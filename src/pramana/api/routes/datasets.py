"""Datasets: upload once, see what code understood, then run analyses against the stored file."""

from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from pramana.api.auth import User
from pramana.api.datasets import DatasetReadError, profile_file
from pramana.api.deps import current_user, get_service
from pramana.api.models import (
    DatasetSummary,
    DatasetView,
    RunView,
    StatementRequest,
    StatementResults,
)
from pramana.api.service import RunService
from pramana.api.v1 import v1_settings

router = APIRouter(prefix="/datasets", tags=["datasets"])
Service = Annotated[RunService, Depends(get_service)]
Owner = Annotated[User, Depends(current_user)]


@router.post("", response_model=DatasetView, status_code=201)
async def upload_dataset(
    service: Service,
    user: Owner,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form(max_length=120)] = None,
) -> DatasetView:
    """Store a bounded CSV/XLSX under a server-generated ID and profile it.

    `name` is the user's label for the dataset; without one the file name is used.
    """
    filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    suffix = Path(filename).suffix.lower()
    name = " ".join((name or "").split()) or filename
    if suffix not in {".csv", ".xlsx"}:
        await file.close()
        raise HTTPException(415, "Upload a CSV or XLSX file.")
    dataset_id = uuid4()
    folder = service.root / "api/datasets" / str(dataset_id)
    path = folder / f"original{suffix}"
    stored = False
    try:
        folder.mkdir(parents=True, exist_ok=True)
        total = 0
        with path.open("xb") as target:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > service.settings.api.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "Upload exceeds the configured size limit.")
                target.write(chunk)
        if total == 0:
            raise HTTPException(422, "The uploaded file is empty.")
        try:
            # Profiling may wait on DeepSeek (the sector reader); run it off the event loop
            # so one upload never stalls every other request.
            view = await run_in_threadpool(
                profile_file,
                path,
                dataset_id=dataset_id,
                name=name,
                size_bytes=total,
                preview_rows=v1_settings().preview_rows,
            )
        except DatasetReadError as error:
            raise HTTPException(422, str(error)) from None
        service.datasets.add(view, path, user.user_id)
        stored = True
        if service.datasets.needs_model_summary(view):
            view = service.datasets.schedule_summary(view)
            background.add_task(service.datasets.refine_summary, dataset_id, user.user_id)
        if service.datasets.needs_measured(view):
            view = service.datasets.schedule_measured(view)
            background.add_task(service.datasets.build_measured, dataset_id, user.user_id)
        elif service.datasets.needs_analyst(view):
            service.datasets.schedule_analyst(view)
            background.add_task(service.datasets.build_analyst, dataset_id, user.user_id)
        return view
    finally:
        await file.close()
        if not stored:
            path.unlink(missing_ok=True)
            if folder.exists() and not any(folder.iterdir()):
                folder.rmdir()


@router.get("", response_model=list[DatasetSummary])
def list_datasets(service: Service, user: Owner) -> list[DatasetSummary]:
    runs = service.repository.list_runs(limit=1000, owner_id=user.user_id)
    return service.datasets.list(runs, user.user_id)


@router.get("/{dataset_id}", response_model=DatasetView)
def get_dataset(
    dataset_id: UUID, service: Service, user: Owner, background: BackgroundTasks
) -> DatasetView:
    try:
        view = service.datasets.get(dataset_id, user.user_id)
        view = service.datasets.backfill_brief(view, user.user_id)
        view = service.datasets.backfill_computed(view, user.user_id)
        if service.datasets.needs_model_summary(view):
            view = service.datasets.schedule_summary(view)
            background.add_task(service.datasets.refine_summary, dataset_id, user.user_id)
        if service.datasets.needs_measured(view):
            view = service.datasets.schedule_measured(view)
            background.add_task(service.datasets.build_measured, dataset_id, user.user_id)
        elif service.datasets.needs_analyst(view):
            service.datasets.schedule_analyst(view)
            background.add_task(service.datasets.build_analyst, dataset_id, user.user_id)
        return view
    except KeyError:
        raise HTTPException(404, "Dataset not found.") from None


@router.get("/{dataset_id}/runs", response_model=list[RunView])
def dataset_runs(dataset_id: UUID, service: Service, user: Owner) -> list[RunView]:
    try:
        service.datasets.get(dataset_id, user.user_id)
    except KeyError:
        raise HTTPException(404, "Dataset not found.") from None
    runs = service.repository.list_runs(limit=1000, owner_id=user.user_id)
    return [r for r in runs if r.dataset_id == dataset_id]


@router.post("/{dataset_id}/runs", response_model=RunView, status_code=202)
def start_run(
    dataset_id: UUID,
    background: BackgroundTasks,
    service: Service,
    user: Owner,
    user_query: Annotated[str | None, Form(max_length=4000)] = None,
) -> RunView:
    """Analyse a stored dataset; one run at a time, and the same gate for every claim."""
    try:
        view = service.datasets.get(dataset_id, user.user_id)
        path = service.datasets.file_path(dataset_id, user.user_id)
    except KeyError:
        raise HTTPException(404, "Dataset not found.") from None
    if view.usable_columns == 0:
        raise HTTPException(422, "No usable measurement columns remain after cleaning.")
    if not service.reserve():
        raise HTTPException(429, "A run is already active; try again after it finishes.")
    try:
        run = service.repository.create(uuid4(), view.name, dataset_id, user.user_id)
        background.add_task(service.execute, run.run_id, path, user_query)
        return run
    except Exception:
        service.release()
        raise


def _tested_pairs(service: RunService, dataset_id: UUID, owner_id: UUID) -> list[dict[str, object]]:
    """Variables and verdicts of the claims the gateway tested in this dataset's latest run."""
    for run in service.repository.list_runs(limit=200, owner_id=owner_id):
        if run.dataset_id != dataset_id or run.status != "completed":
            continue
        try:
            results = service.repository.results(run.run_id, owner_id)
        except KeyError:
            return []
        out: list[dict[str, object]] = []
        for row in [*(results.verified_insights if results else []), *(results.rejected_claims if results else [])]:
            chart = row.chart
            if chart is None:
                continue
            pair = (chart.x, chart.y) if chart.kind == "scatter" else (chart.group, chart.value)
            out.append({"x": pair[0], "y": pair[1], "verdict": row.proof.verdict.value, "q": row.proof.q_value})
        return out
    return []


@router.post("/{dataset_id}/statements", response_model=StatementResults)
def check_statements(
    dataset_id: UUID, body: StatementRequest, service: Service, user: Owner
) -> StatementResults:
    """Check what a sentence claims: a model reads it, code recomputes it from the table."""
    try:
        service.datasets.get(dataset_id, user.user_id)
    except KeyError:
        raise HTTPException(404, "Dataset not found.") from None
    try:
        checked, notes = service.datasets.check_text(
            dataset_id, user.user_id, body.text, _tested_pairs(service, dataset_id, user.user_id)
        )
    except ValueError as problem:
        raise HTTPException(422, str(problem)) from None
    return StatementResults(results=checked, notes=notes)
