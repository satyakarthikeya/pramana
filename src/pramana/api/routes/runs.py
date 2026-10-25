"""POST upload/run, GET run status. Every run belongs to the signed-in user."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)

from pramana.api.auth import User
from pramana.api.deps import current_user, get_service
from pramana.api.models import RunView
from pramana.api.routes.system import model_blockers
from pramana.api.service import RunService

router = APIRouter(prefix="/runs", tags=["runs"])
Service = Annotated[RunService, Depends(get_service)]
Owner = Annotated[User, Depends(current_user)]


@router.post("", response_model=RunView, status_code=202)
async def create_run(
    background: BackgroundTasks,
    service: Service,
    user: Owner,
    file: Annotated[UploadFile, File()],
    user_query: Annotated[str | None, Form(max_length=4000)] = None,
) -> RunView:
    """Accept a bounded CSV/XLSX upload under a server-generated UUID and start one run."""
    file_name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    suffix = Path(file_name).suffix.lower()
    if suffix not in {".csv", ".xlsx"}:
        await file.close()
        raise HTTPException(415, "Upload a CSV or XLSX file.")
    if blockers := model_blockers():
        await file.close()
        raise HTTPException(
            503, "The configured analysis model cannot run: " + "; ".join(blockers) + "."
        )
    if not service.reserve():
        await file.close()
        raise HTTPException(429, "A run is already active; try again after it finishes.")
    path = service.root / "api/uploads" / f"{uuid4()}{suffix}"
    created = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with path.open("xb") as target:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > service.settings.api.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, "Upload exceeds the configured size limit.")
                target.write(chunk)
        if total == 0:
            raise HTTPException(422, "The uploaded file is empty.")
        view = service.repository.create(uuid4(), file_name, None, user.user_id)
        background.add_task(service.execute, view.run_id, path, user_query)
        created = True
        return view
    finally:
        await file.close()
        if not created:
            path.unlink(missing_ok=True)
            service.release()


@router.get("", response_model=list[RunView])
def list_runs(
    service: Service,
    user: Owner,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RunView]:
    """List persisted run metadata; no candidate claims are exposed here."""
    return service.repository.list_runs(limit, offset, user.user_id)


@router.get("/{run_id}", response_model=RunView)
def get_run(run_id: UUID, service: Service, user: Owner) -> RunView:
    """Return a run's persisted status without rerunning its analysis."""
    try:
        return service.repository.get(run_id, user.user_id)
    except KeyError:
        raise HTTPException(404, "Run not found.") from None
