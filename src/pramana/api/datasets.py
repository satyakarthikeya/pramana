"""Stored datasets with a cheap profile computed at upload time, before any run or model call."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
from pydantic import ValidationError

from pramana.analysis.analyst.models import ANALYST_VERSION, AnalystRead
from pramana.analysis.computed import (
    COMPUTED_VERSION,
    ComputedAnalysis,
    compute_analysis,
    load_computed_config,
)
from pramana.analysis.computed.summary import summarise
from pramana.analysis.measured import (
    MEASURED_VERSION,
    MeasuredAnalysis,
    compute_measured,
    load_measured_config,
)
from pramana.analysis.reader import DataBrief, read_data
from pramana.analysis.schema_inference import SchemaProfile
from pramana.analysis.sector_model import detect_sector_with_model
from pramana.analysis.sectors import load_packs, pack_for
from pramana.analysis.shape import classify_shape
from pramana.api.charts import data_overview
from pramana.api.models import (
    ColumnPreview,
    DataPreview,
    DatasetSummary,
    DatasetView,
    RunView,
)
from pramana.common.logging import get_logger

logger = get_logger(component="datasets")

MAX_PREVIEW_COLUMNS = 40
MAX_LISTED_COLUMNS = 100


class DatasetReadError(ValueError):
    """A fixed, safe-to-display message; never raw exception text, paths or rows."""


def build_preview(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    removed: Sequence[Mapping[str, Any]],
    preview_rows: int,
) -> DataPreview:
    """Bound what is shown about a cleaned table: detected roles, exclusions and a few rows."""
    columns = [
        ColumnPreview(
            name=name,
            role=column.role.value,
            usable=column.usable_for_hypotheses,
            reasons=column.reasons,
        )
        for name, column in schema.columns.items()
    ]
    columns.extend(
        ColumnPreview(name=item["column"], role="excluded", usable=False, reasons=[item["reason"]])
        for item in removed
    )
    source = frame.iloc[:preview_rows, :MAX_PREVIEW_COLUMNS].astype(object)
    shown = source.where(source.notna(), "").astype(str)
    rows = [
        {str(key): str(value)[:160] for key, value in row.items()}
        for row in shown.to_dict(orient="records")
    ]
    return DataPreview(
        rows=len(frame),
        columns=len(frame.columns),
        detected_columns=columns[:MAX_LISTED_COLUMNS],
        sample_rows=rows,
        omitted_columns=max(0, len(columns) - MAX_LISTED_COLUMNS),
    )


def exact_tier(
    frame: pd.DataFrame, schema: SchemaProfile, *, trace_id: UUID
) -> ComputedAnalysis | None:
    """The Exact tier for a cleaned table, or None if it cannot be built at all.

    The sector is private to the system: with `sector_engine: api` DeepSeek picks it
    from column names (traced under `trace_id`, the dataset's id), otherwise the rules
    do. Each analysis already fails on its own; this only guards detection and shape,
    so a strange table can lose the section but never the upload.
    """
    try:
        config = load_computed_config()
        packs = load_packs()
        detected = None
        if config.sector_engine == "api":
            detected = detect_sector_with_model(frame, schema, packs, trace_id=trace_id)
        return compute_analysis(frame, schema, config=config, packs=packs, detected=detected)
    except Exception:
        logger.exception("exact_tier_failed")
        return None


def compute_exact_tier(path: Path, *, trace_id: UUID) -> ComputedAnalysis | None:
    """Rebuild the Exact tier for a stored file, or None if it cannot be read."""
    from pramana.analysis import clean_dataset, infer_schema, load_config, load_dataset

    try:
        cleaned, _ = clean_dataset(load_dataset(path))
        schema = infer_schema(cleaned, load_config().schema_inference)
    except Exception:
        return None
    return exact_tier(cleaned, schema, trace_id=trace_id)


def measured_tier(
    frame: pd.DataFrame, schema: SchemaProfile, computed: ComputedAnalysis | None
) -> MeasuredAnalysis | None:
    """The Measured tier for a cleaned table, or None if it cannot be built at all.

    Uses the shape and sector roles the Exact tier already found (the user sees the
    same ones); without an Exact tier the shape is classified here and no roles are
    known. Each analysis fails on its own; this only guards the setup.
    """
    try:
        if computed is not None:
            shape, roles = computed.shape, dict(computed.sector.roles)
            pack = pack_for(computed.sector, load_packs())
            additive, measures = pack.additive_measures, pack.measures
        else:
            shape, roles, additive, measures = classify_shape(frame, schema), {}, True, []
        return compute_measured(
            frame,
            schema,
            shape,
            config=load_measured_config(),
            roles=roles,
            additive=additive,
            measure_roles=measures,
        )
    except Exception:
        logger.exception("measured_tier_failed")
        return None


def compute_measured_tier(path: Path, computed: ComputedAnalysis | None) -> MeasuredAnalysis | None:
    """Build the Measured tier for a stored file, or None if it cannot be read."""
    from pramana.analysis import clean_dataset, infer_schema, load_config, load_dataset

    try:
        cleaned, _ = clean_dataset(load_dataset(path))
        schema = infer_schema(cleaned, load_config().schema_inference)
    except Exception:
        return None
    return measured_tier(cleaned, schema, computed)


def _tier_setup(
    frame: pd.DataFrame, schema: SchemaProfile, computed: ComputedAnalysis | None
) -> tuple[Any, dict[str, str], bool, Any]:
    """Shape, sector roles, additivity and measure roles shared by the Measured tier and the
    analyst's extra analyses, so both see the same table the user sees."""
    if computed is not None:
        pack = pack_for(computed.sector, load_packs())
        return computed.shape, dict(computed.sector.roles), pack.additive_measures, pack.measures
    return classify_shape(frame, schema), {}, True, []


def analyst_tier(
    path: Path,
    computed: ComputedAnalysis | None,
    measured: MeasuredAnalysis | None,
    *,
    trace_id: UUID,
) -> tuple[MeasuredAnalysis | None, AnalystRead | None]:
    """The analyst agent's step: it may ask for extra analyses (code lints and runs them),
    then reads every result in words. Never raises; with the model off, the read is the
    code's own sentences and no extra analysis is run."""
    from pramana.analysis import clean_dataset, infer_schema, load_config, load_dataset
    from pramana.analysis.analyst.facts import build_facts
    from pramana.analysis.analyst.read import build_read, choose_requests

    try:
        cleaned, _ = clean_dataset(load_dataset(path))
        schema = infer_schema(cleaned, load_config().schema_inference)
        engine = load_computed_config().analyst_engine
        shape, roles, additive, measures = _tier_setup(cleaned, schema, computed)
        record: list = []
        if engine != "template" and measured is not None:
            config = load_measured_config()
            requests, record = choose_requests(
                cleaned, schema, shape, roles, measured, config, trace_id=trace_id
            )
            if requests:
                extra = compute_measured(
                    cleaned,
                    schema,
                    shape,
                    config=config,
                    roles=roles,
                    requests=requests,
                    additive=additive,
                    measure_roles=measures,
                )
                measured = measured.model_copy(update={"items": [*measured.items, *extra.items]})
        facts = build_facts(computed, measured, cleaned, schema)
        names = [str(c) for c in cleaned.columns]
        read = None
        reason = None
        if engine == "agent":
            from pramana.analysis.analyst.agentic import agentic_read
            from pramana.analysis.workspace import load_workspace_config

            try:
                read = agentic_read(
                    cleaned,
                    schema,
                    load_config().hypotheses,
                    load_workspace_config(),
                    facts,
                    names,
                    record,
                    trace_id=trace_id,
                    time_column=shape.time_column,
                    additive=additive,
                )
            except Exception as problem:
                logger.warning("agentic_read_failed", reason=str(problem)[:200])
                reason = f"the tool-using agent could not finish ({str(problem)[:120]})"
        if read is None:
            read = build_read(
                facts,
                names,
                record,
                trace_id=trace_id,
                engine="template" if engine == "template" else "api",
            )
            if reason and read.fallback_reason is None:
                read = read.model_copy(update={"fallback_reason": reason})
        return measured, read
    except Exception:
        logger.exception("analyst_tier_failed")
        return measured, None


def compute_brief(path: Path) -> DataBrief | None:
    """Rebuild the Data Reader's brief for a stored file, or None if it cannot be read."""
    from pramana.analysis import clean_dataset, infer_schema, load_config, load_dataset

    try:
        cleaned, _ = clean_dataset(load_dataset(path))
        return read_data(cleaned, infer_schema(cleaned, load_config().schema_inference))
    except Exception:
        return None


def profile_file(
    path: Path, *, dataset_id: UUID, name: str, size_bytes: int, preview_rows: int
) -> DatasetView:
    """Read, clean and describe one table with deterministic code only."""
    from pramana.analysis import clean_dataset, infer_schema, load_config, load_dataset

    try:
        frame = load_dataset(path)
    except Exception:
        raise DatasetReadError(
            "The file could not be read as a table. Check its format, encoding and row limit."
        ) from None
    if frame.empty:
        raise DatasetReadError("The file has no data rows. Upload a table with measurements.")
    cleaned, report = clean_dataset(frame)
    schema = infer_schema(cleaned, load_config().schema_inference)
    usable = schema.usable()
    removed = report.model_dump(mode="json").get("columns_removed", [])
    preview = build_preview(cleaned, schema, removed, preview_rows)
    # The overview and the brief are derived extras: odd data may stop them, never the upload.
    try:
        overview = data_overview(cleaned, usable)
    except Exception:
        overview = None
    try:
        brief = read_data(cleaned, schema)
    except Exception:
        brief = None
    computed = exact_tier(cleaned, schema, trace_id=dataset_id)
    return DatasetView(
        dataset_id=dataset_id,
        name=name,
        created_at=datetime.now(UTC),
        size_bytes=size_bytes,
        usable_columns=len(usable),
        preview=preview,
        overview=overview,
        brief=brief,
        computed=computed,
        computed_failed_version=COMPUTED_VERSION if computed is None else 0,
    )


class DatasetRepository:
    """Persist dataset profiles beside run metadata; the original file stays on disk."""

    def __init__(self, path: Path) -> None:
        self.path = path
        #: Datasets whose Measured tier this process is building right now; a pending
        #: flag stored by a process that has since stopped is therefore stale.
        self._measuring: set[UUID] = set()
        self._analysing: set[UUID] = set()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY, view_json TEXT NOT NULL, file_path TEXT NOT NULL)""")
            if "owner_id" not in {r[1] for r in connection.execute("PRAGMA table_info(datasets)")}:
                connection.execute("ALTER TABLE datasets ADD COLUMN owner_id TEXT")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    @staticmethod
    def _load(raw: str) -> DatasetView:
        """Read a stored view; a brief or Exact tier from an older version is dropped.

        Both are derived data, rebuilt from the stored file on next open, so a format
        change must never make a saved dataset unreadable.
        """
        try:
            return DatasetView.model_validate_json(raw)
        except ValidationError:
            data = json.loads(raw)
            for derived in ("brief", "computed", "measured"):
                try:
                    DatasetView.model_validate(
                        {
                            **data,
                            "brief": None,
                            "computed": None,
                            "measured": None,
                            derived: data.get(derived),
                        }
                    )
                except ValidationError:
                    data.pop(derived, None)
            return DatasetView.model_validate(data)

    def add(self, view: DatasetView, file_path: Path, owner_id: UUID | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO datasets (dataset_id, view_json, file_path, owner_id) "
                "VALUES (?, ?, ?, ?)",
                (
                    str(view.dataset_id),
                    view.model_dump_json(),
                    str(file_path),
                    str(owner_id) if owner_id else None,
                ),
            )

    def _column(self, column: str, dataset_id: UUID, owner_id: UUID | None) -> str:
        """One column of a dataset; KeyError when missing or owned by someone else."""
        query, args = f"SELECT {column} FROM datasets WHERE dataset_id = ?", [str(dataset_id)]
        if owner_id is not None:
            query += " AND owner_id = ?"
            args.append(str(owner_id))
        with self._connect() as connection:
            row = connection.execute(query, args).fetchone()
        if row is None:
            raise KeyError(str(dataset_id))
        return str(row[0])

    def get(self, dataset_id: UUID, owner_id: UUID | None = None) -> DatasetView:
        return self._load(self._column("view_json", dataset_id, owner_id))

    def file_path(self, dataset_id: UUID, owner_id: UUID | None = None) -> Path:
        return Path(self._column("file_path", dataset_id, owner_id))

    def backfill_brief(self, view: DatasetView, owner_id: UUID | None = None) -> DatasetView:
        """Add the Data Reader's brief to a dataset stored before it existed."""
        if view.brief is not None:
            return view
        brief = compute_brief(self.file_path(view.dataset_id, owner_id))
        if brief is None:
            return view
        updated = view.model_copy(update={"brief": brief})
        with self._connect() as connection:
            connection.execute(
                "UPDATE datasets SET view_json = ? WHERE dataset_id = ?",
                (updated.model_dump_json(), str(view.dataset_id)),
            )
        return updated

    def _save(self, view: DatasetView) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE datasets SET view_json = ? WHERE dataset_id = ?",
                (view.model_dump_json(), str(view.dataset_id)),
            )

    def backfill_computed(self, view: DatasetView, owner_id: UUID | None = None) -> DatasetView:
        """Add the Exact tier to a dataset stored before it existed, or built by an older
        `COMPUTED_VERSION` (new figures or chart data), or stored in a stale format."""
        if view.computed is not None and view.computed.version >= COMPUTED_VERSION:
            return view
        if view.computed_failed_version >= COMPUTED_VERSION:
            return view  # this version was already tried and could not be built
        computed = compute_exact_tier(
            self.file_path(view.dataset_id, owner_id), trace_id=view.dataset_id
        )
        update: dict[str, object] = (
            {"computed_failed_version": COMPUTED_VERSION}
            if computed is None
            else {"computed": computed, "computed_failed_version": 0}
        )
        updated = view.model_copy(update=update)
        self._save(updated)
        return updated

    @staticmethod
    def needs_model_summary(view: DatasetView) -> bool:
        """A code summary the model has not tried to reword, none scheduled, model on."""
        summary = view.computed.summary if view.computed else None
        return (
            summary is not None
            and summary.source == "template"
            and summary.fallback_reason is None
            and not summary.pending
            and load_computed_config().summary_engine == "api"
        )

    def schedule_summary(self, view: DatasetView) -> DatasetView:
        """Mark the summary as pending before the background task is queued, so a second
        open while the model is working does not queue another call."""
        assert view.computed is not None and view.computed.summary is not None
        summary = view.computed.summary.model_copy(update={"pending": True})
        updated = view.model_copy(
            update={"computed": view.computed.model_copy(update={"summary": summary})}
        )
        self._save(updated)
        return updated

    def refine_summary(self, dataset_id: UUID, owner_id: UUID | None = None) -> None:
        """Replace the code summary with DeepSeek's wording, or record why it was not used.

        Runs after the response (a background task), so the upload never waits on it.
        The outcome is stored either way, so a failing model is not asked on every open.
        The view is read again just before saving, and nothing is written if the analysis
        was rebuilt meanwhile, so a slow model reply never overwrites newer figures.
        """
        try:
            view = self.get(dataset_id, owner_id)
        except KeyError:
            return
        summary = view.computed.summary if view.computed else None
        if view.computed is None or summary is None or not summary.pending:
            return
        version = view.computed.version
        refined = summarise(view.computed, engine="api", trace_id=dataset_id)
        latest = self.get(dataset_id, owner_id)
        if latest.computed is None or latest.computed.version != version:
            return
        computed = latest.computed.model_copy(update={"summary": refined})
        self._save(latest.model_copy(update={"computed": computed}))

    def needs_measured(self, view: DatasetView) -> bool:
        """The Measured tier is missing or older than `MEASURED_VERSION`, was not already
        tried at this version without success, and no build is running in this process."""
        if not load_measured_config().enabled or view.dataset_id in self._measuring:
            return False
        if view.measured is not None and view.measured.version >= MEASURED_VERSION:
            return False
        return view.measured_failed_version < MEASURED_VERSION

    def schedule_measured(self, view: DatasetView) -> DatasetView:
        """Mark the Measured build as pending before the background task is queued, so a
        second open while it runs does not queue another."""
        self._measuring.add(view.dataset_id)
        updated = view.model_copy(update={"measured_pending": True})
        self._save(updated)
        return updated

    def build_measured(self, dataset_id: UUID, owner_id: UUID | None = None) -> None:
        """Compute the Measured tier for a stored dataset and store it (a background task).

        The outcome is stored either way (a failure records the version so it is not
        retried on every open), and the view is read again just before saving, so a
        slow build never overwrites a summary or Exact tier written meanwhile.
        """
        try:
            try:
                view = self.get(dataset_id, owner_id)
                path = self.file_path(dataset_id, owner_id)
            except KeyError:
                return
            measured = compute_measured_tier(path, view.computed)
            latest = self.get(dataset_id, owner_id)
            update: dict[str, object] = (
                {"measured_failed_version": MEASURED_VERSION}
                if measured is None
                else {"measured": measured, "measured_failed_version": 0}
            )
            self._save(latest.model_copy(update={**update, "measured_pending": False}))
        except Exception:
            logger.exception("measured_build_failed")
        finally:
            self._measuring.discard(dataset_id)
        self._analysing.add(dataset_id)
        self.build_analyst(dataset_id, owner_id)

    def check_text(
        self,
        dataset_id: UUID,
        owner_id: UUID | None,
        text: str,
        tested: list[dict[str, Any]],
    ) -> tuple[list[Any], list[str]]:
        """Read a sentence into structured statements (a model) and recompute each (code).

        Raises `ValueError` with a safe message when the model cannot read the sentence.
        """
        from pramana.analysis import clean_dataset, infer_schema, load_config, load_dataset
        from pramana.analysis.statements.check import check_statement
        from pramana.analysis.statements.models import CheckedStatement
        from pramana.analysis.statements.parse import parse_statements

        view = self.get(dataset_id, owner_id)
        cleaned, _ = clean_dataset(load_dataset(self.file_path(dataset_id, owner_id)))
        schema = infer_schema(cleaned, load_config().schema_inference)
        shape, _, additive, _ = _tier_setup(cleaned, schema, view.computed)
        statements, notes = parse_statements(
            text, cleaned, schema, time_column=shape.time_column, trace_id=dataset_id
        )
        checked = [
            CheckedStatement(
                statement=s.model_dump(mode="json", exclude_none=True),
                result=check_statement(
                    s, cleaned, time_column=shape.time_column, additive=additive, tested=tested
                ),
            )
            for s in statements
        ]
        return checked, notes

    def needs_analyst(self, view: DatasetView) -> bool:
        """A Measured tier exists and the analyst has not read it at this version."""
        if view.measured is None or view.dataset_id in self._measuring:
            return False
        if view.dataset_id in self._analysing:
            return False
        return view.analyst is None or view.analyst.version < ANALYST_VERSION

    def schedule_analyst(self, view: DatasetView) -> None:
        """Claim the analyst step before the background task is queued, so a second open
        while the model works does not queue another."""
        self._analysing.add(view.dataset_id)

    def build_analyst(self, dataset_id: UUID, owner_id: UUID | None = None) -> None:
        """Let the analyst agent add analyses and read the results (a background task).

        The view is read again just before saving, so a slow model never overwrites a
        newer tier. The result is stored even when the model was not used (a code read), so
        a failing model is not asked on every open.
        """
        try:
            try:
                view = self.get(dataset_id, owner_id)
                path = self.file_path(dataset_id, owner_id)
            except KeyError:
                return
            if view.measured is None or (
                view.analyst is not None and view.analyst.version >= ANALYST_VERSION
            ):
                return
            measured, read = analyst_tier(path, view.computed, view.measured, trace_id=dataset_id)
            if read is None:
                return
            latest = self.get(dataset_id, owner_id)
            if latest.measured is None or latest.measured.version != view.measured.version:
                return
            self._save(latest.model_copy(update={"measured": measured, "analyst": read}))
        except Exception:
            logger.exception("analyst_build_failed")
        finally:
            self._analysing.discard(dataset_id)

    def claim_unowned(self, owner_id: UUID) -> None:
        """Hand datasets stored before accounts existed to the first account."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE datasets SET owner_id = ? WHERE owner_id IS NULL", (str(owner_id),)
            )

    def list(
        self, runs: Sequence[RunView], owner_id: UUID | None = None, limit: int = 100
    ) -> list[DatasetSummary]:
        """Newest first, each with how many runs it has and the latest run's status."""
        where, args = ("", []) if owner_id is None else (" WHERE owner_id = ?", [str(owner_id)])
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT view_json FROM datasets{where} ORDER BY rowid DESC LIMIT ?",
                [*args, limit],
            ).fetchall()
        summaries = []
        for row in rows:
            view = self._load(row[0])
            mine = [run for run in runs if run.dataset_id == view.dataset_id]
            summaries.append(
                DatasetSummary(
                    dataset_id=view.dataset_id,
                    name=view.name,
                    created_at=view.created_at,
                    rows=view.preview.rows,
                    columns=view.preview.columns,
                    run_count=len(mine),
                    last_status=mine[0].status if mine else None,
                )
            )
        return summaries
