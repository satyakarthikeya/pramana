"""API integration uses public graph adapters without changing orchestration contracts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any
from uuid import UUID

from pramana.analysis.schema_inference import SchemaProfile
from pramana.api.models import ResultRow, RunResults
from pramana.api.repository import RunRepository
from pramana.common.logging import get_logger
from pramana.contracts import ProofObject, Verdict
from pramana.memory.config import MemorySettings
from pramana.memory.fingerprint import fingerprint_schema
from pramana.memory.store import ChromaLessonStore
from pramana.orchestration.adapters import (
    celery_verification_adapter,
    inprocess_verification_adapter,
)
from pramana.orchestration.graph import build_graph, run_graph
from pramana.orchestration.integration import configured_adapters
from pramana.orchestration.run_lifecycle import new_run
from pramana.orchestration.state import PramanaState, RunStatus


class RunService:
    """Bound local runs, preserve the full verification family, and persist only guarded results."""

    def __init__(
        self,
        root: Path,
        settings: MemorySettings,
        *,
        store: ChromaLessonStore | None = None,
        runner: Callable[[UUID, Path, str | None], PramanaState] | None = None,
    ) -> None:
        self.root = root
        self.settings = settings
        self.repository = RunRepository(root / "api/runs.sqlite3")
        self.store = store or ChromaLessonStore(settings)
        self._slots = BoundedSemaphore(settings.api.max_active_runs)
        self._runner = runner or self._run_workflow

    def reserve(self) -> bool:
        """Refuse excess local execution instead of starting unbounded background jobs."""
        return self._slots.acquire(blocking=False)

    def release(self) -> None:
        """Return a previously reserved execution slot."""
        self._slots.release()

    def _run_workflow(self, run_id: UUID, path: Path, query: str | None) -> PramanaState:
        state = new_run(str(path), user_query=query)
        state.run_id = run_id

        def memory_write(current: PramanaState, proofs: Sequence[ProofObject]) -> dict[str, Any]:
            if not proofs:
                return {"memory_receipts": []}
            schema = SchemaProfile.model_validate(current.schema_profile)
            lessons = self.store.write_lessons(
                current.candidate_insights,
                proofs,
                run_id=str(current.run_id),
                dataset_ref=str(current.dataset_ref),
                fingerprint=fingerprint_schema(schema),
            )
            return {
                "memory_receipts": [
                    {
                        "record_id": lesson.record_id,
                        "insight_id": lesson.proof.insight_id,
                        "backend": "chromadb",
                    }
                    for lesson in lessons
                ]
            }

        verify = (
            inprocess_verification_adapter
            if self.settings.api.verification_mode == "inprocess"
            else celery_verification_adapter
        )
        adapters = configured_adapters(verify=verify, memory_write=memory_write, data_dir=self.root)
        return run_graph(state, build_graph(adapters))

    def execute(self, run_id: UUID, path: Path, query: str | None) -> None:
        """Record failures as failures; never publish candidates that lack a proof."""
        try:
            self.repository.update(run_id, RunStatus.RUNNING)
            state = self._runner(run_id, path, query)
            if state.run_id != run_id:
                raise ValueError("runner returned a different run")
            candidates = {item.insight_id: item for item in state.candidate_insights}
            rows = []
            seen: set[str] = set()
            for item in state.proof_objects:
                proof = ProofObject.model_validate(item.model_dump(mode="python"))
                candidate = candidates.get(proof.insight_id)
                if (
                    candidate is None
                    or proof.insight_id in seen
                    or candidate.dataset_ref != state.dataset_ref
                ):
                    raise ValueError("proof does not match the run's unique verified candidates")
                seen.add(proof.insight_id)
                rows.append(
                    ResultRow(insight_id=proof.insight_id, claim=candidate.claim, proof=proof)
                )
            if state.status not in {RunStatus.COMPLETED, RunStatus.DEGRADED, RunStatus.FAILED}:
                raise ValueError("runner did not finish")
            if state.status is RunStatus.COMPLETED and len(seen) != len(candidates):
                raise ValueError("completed run has candidates without proofs")
            results = RunResults(
                run=self.repository.get(run_id),
                verified_insights=[row for row in rows if row.proof.verdict is Verdict.PASS],
                rejected_claims=[row for row in rows if row.proof.verdict is Verdict.REJECT],
                candidate_count=len(candidates),
                unverified_candidate_count=len(candidates) - len(seen),
            )
            error = (
                "Some workflow steps failed; inspect the local run logs." if state.errors else None
            )
            self.repository.update(run_id, state.status, error=error, results=results)
        except Exception as error:
            get_logger(component="api", run_id=str(run_id)).error(
                "api_run_failed", error_type=type(error).__name__
            )
            # Do not expose arbitrary exception messages (paths, raw rows or credentials).
            self.repository.update(
                run_id, RunStatus.FAILED, error="Run failed; no unverified findings are published."
            )
        finally:
            self.release()
