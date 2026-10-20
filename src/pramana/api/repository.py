"""SQLite run metadata and completed result snapshots; never stores raw dataframes."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pramana.api.models import RunResults, RunView
from pramana.orchestration.state import RunStatus


class RunRepository:
    """Persist run status/results across local API restarts without replaying runs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, view_json TEXT NOT NULL, results_json TEXT)""")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def create(self, run_id: UUID, file_name: str) -> RunView:
        """Insert one pending run; never overwrite an existing run ID."""
        view = RunView(
            run_id=run_id,
            status=RunStatus.PENDING,
            file_name=file_name,
            created_at=datetime.now(UTC),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs VALUES (?, ?, NULL)", (str(run_id), view.model_dump_json())
            )
        return view

    def get(self, run_id: UUID) -> RunView:
        """Return one persisted status, raising KeyError for an unknown run."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT view_json FROM runs WHERE run_id = ?", (str(run_id),)
            ).fetchone()
        if row is None:
            raise KeyError(str(run_id))
        return RunView.model_validate_json(row[0])

    def list_runs(self, limit: int = 50, offset: int = 0) -> list[RunView]:
        """Return bounded recent run metadata without any unverified claim text."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT view_json FROM runs ORDER BY rowid DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
        return [RunView.model_validate_json(row[0]) for row in rows]

    def progress(self, run_id: UUID, stage: str, **details: Any) -> None:
        """Persist bounded product progress without exposing unverified candidate claims."""
        view = self.get(run_id)
        if view.status not in {RunStatus.PENDING, RunStatus.RUNNING}:
            return
        view = RunView.model_validate({**view.model_dump(), **details, "progress": stage})
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET view_json = ? WHERE run_id = ?",
                (view.model_dump_json(), str(run_id)),
            )

    def update(
        self,
        run_id: UUID,
        status: RunStatus,
        *,
        error: str | None = None,
        results: RunResults | None = None,
    ) -> None:
        """Atomically persist status and matching completed results."""
        view = self.get(run_id)
        terminal = status in {RunStatus.COMPLETED, RunStatus.DEGRADED, RunStatus.FAILED}
        view = RunView.model_validate(
            {
                **view.model_dump(),
                "status": status,
                "error": error,
                "finished_at": datetime.now(UTC) if terminal else None,
                "progress": "Finished" if terminal else view.progress,
            }
        )
        payload = None
        if results is not None:
            payload = json.dumps(
                {**results.model_dump(mode="json"), "run": view.model_dump(mode="json")}
            )
        with self._connect() as connection:
            connection.execute(
                "UPDATE runs SET view_json = ?, results_json = ? WHERE run_id = ?",
                (view.model_dump_json(), payload, str(run_id)),
            )

    def results(self, run_id: UUID) -> RunResults | None:
        """Return stored results, never rerun analysis to satisfy a GET request."""
        self.get(run_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT results_json FROM runs WHERE run_id = ?", (str(run_id),)
            ).fetchone()
        return RunResults.model_validate_json(row[0]) if row and row[0] else None

    def recover_interrupted(self) -> None:
        """Mark unfinished jobs failed at startup; do not silently resubmit hypotheses."""
        with self._connect() as connection:
            rows = connection.execute("SELECT view_json FROM runs").fetchall()
        for row in rows:
            view = RunView.model_validate_json(row[0])
            if view.status in {RunStatus.PENDING, RunStatus.RUNNING}:
                self.update(
                    view.run_id,
                    RunStatus.FAILED,
                    error="API restarted before this run finished; start a new run.",
                )
