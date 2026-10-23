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

from pramana.analysis.computed import ComputedAnalysis, compute_analysis, load_computed_config
from pramana.analysis.reader import DataBrief, read_data
from pramana.analysis.schema_inference import SchemaProfile
from pramana.analysis.sector_model import detect_sector_with_model
from pramana.analysis.sectors import load_packs
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
    )


class DatasetRepository:
    """Persist dataset profiles beside run metadata; the original file stays on disk."""

    def __init__(self, path: Path) -> None:
        self.path = path
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
            for derived in ("brief", "computed"):
                try:
                    DatasetView.model_validate({**data, "brief": None, "computed": None,
                                                derived: data.get(derived)})
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
        """Add the Exact tier to a dataset stored before it existed (or with a stale one)."""
        if view.computed is not None:
            return view
        computed = compute_exact_tier(
            self.file_path(view.dataset_id, owner_id), trace_id=view.dataset_id
        )
        if computed is None:
            return view
        updated = view.model_copy(update={"computed": computed})
        self._save(updated)
        return updated

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
