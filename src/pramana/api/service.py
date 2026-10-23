"""API integration uses public graph adapters without changing orchestration contracts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any
from uuid import UUID

from pramana.advisory.explainer import ChatFn as AdvisoryChatFn
from pramana.advisory.findings import Finding
from pramana.advisory.models import AdvisoryReport
from pramana.advisory.run import advise
from pramana.analysis.schema_inference import SchemaProfile
from pramana.analysis.workspace.agent import ChatFn
from pramana.analysis.workspace.ledger import ExplorationSummary
from pramana.api.auth import AuthService
from pramana.api.charts import claim_chart
from pramana.api.datasets import DatasetRepository, build_preview
from pramana.api.models import DataPreview, ResultRow, RunResults
from pramana.api.repository import RunRepository
from pramana.api.v1 import effect_strength, permutation_count, rejection_reason, v1_settings
from pramana.chat.service import ChatService, Verifier
from pramana.common.logging import get_logger
from pramana.contracts import ProofObject, Verdict
from pramana.memory.config import MemorySettings
from pramana.memory.fingerprint import fingerprint_schema
from pramana.memory.store import ChromaLessonStore
from pramana.orchestration.adapters import (
    celery_verification_adapter,
    inprocess_verification_adapter,
)
from pramana.orchestration.analysis_integration import native_analysis_adapters
from pramana.orchestration.graph import build_graph, run_graph
from pramana.orchestration.integration import configured_adapters
from pramana.orchestration.memory_integration import MemoryIntegration
from pramana.orchestration.run_lifecycle import new_run
from pramana.orchestration.state import PramanaState, RunStatus


class DataInputError(ValueError):
    """A fixed, safe-to-display V1 data-quality message, not raw exception text."""


def data_preview(state: PramanaState) -> DataPreview:
    """Expose a bounded cleaned-data preview, not proposed or verified insights."""
    schema = SchemaProfile.model_validate(state.schema_profile)
    removed = state.cleaning_report.get("columns_removed", [])
    return build_preview(state.dataset, schema, removed, v1_settings().preview_rows)


class RunService:
    """Bound local runs, preserve the full verification family, and persist only guarded results."""

    def __init__(
        self,
        root: Path,
        settings: MemorySettings,
        *,
        store: ChromaLessonStore | None = None,
        runner: Callable[[UUID, Path, str | None], PramanaState] | None = None,
        chat: ChatFn | None = None,
        chat_verifier: Verifier | None = None,
        advisory_chat: AdvisoryChatFn | None = None,
    ) -> None:
        self.root = root
        self.settings = settings
        self.repository = RunRepository(root / "api/runs.sqlite3")
        self.datasets = DatasetRepository(root / "api/runs.sqlite3")
        self.auth = AuthService(root / "api/runs.sqlite3")
        self.store = store or ChromaLessonStore(settings)
        self._slots = BoundedSemaphore(settings.api.max_active_runs)
        self._runner = runner or self._run_workflow
        self._advisory_chat = advisory_chat
        self.chat = ChatService(
            root / "api/runs.sqlite3",
            self.datasets,
            self.repository,
            reserve=self.reserve,
            release=self.release,
            chat=chat,
            verifier=chat_verifier,
        )

    def reserve(self) -> bool:
        """Refuse excess local execution instead of starting unbounded background jobs."""
        return self._slots.acquire(blocking=False)

    def release(self) -> None:
        """Return a previously reserved execution slot."""
        self._slots.release()

    def _run_workflow(self, run_id: UUID, path: Path, query: str | None) -> PramanaState:
        state = new_run(str(path), user_query=query)
        state.run_id = run_id
        state.episode_mode = True  # Automatic hints; there is no episode-selection UI in V1.

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

        def verify(current: PramanaState) -> Any:
            self.repository.progress(run_id, f"Testing {len(current.candidate_insights)} claims")
            if self.settings.api.verification_mode == "inprocess":
                return inprocess_verification_adapter(
                    current,
                    progress=lambda i, total: self.repository.progress(
                        run_id, f"Checking claim {i} of {total}"
                    ),
                )
            return celery_verification_adapter(current)

        adapters = configured_adapters(
            verify=verify,
            memory_write=memory_write,
            data_dir=self.root,
            analysis=native_analysis_adapters(
                data_dir=self.root, candidate_limit=v1_settings().max_candidates
            ),
            memory=MemoryIntegration(self.store),
        )

        def ingest(current: PramanaState) -> Any:
            self.repository.progress(run_id, "Reading data")
            result = dict(adapters.ingest(current))
            if result["dataset"].empty:
                raise DataInputError("The file has no data rows. Upload a table with measurements.")
            return result

        def prepare(current: PramanaState) -> Any:
            self.repository.progress(run_id, "Cleaning data and detecting column types")
            result = dict(adapters.subagents(current))
            prepared = PramanaState.model_validate({**current.model_dump(), **result})
            schema = SchemaProfile.model_validate(prepared.schema_profile)
            preview = data_preview(prepared)
            self.repository.progress(
                run_id,
                "Data preview ready",
                preview=preview,
                past_lessons=prepared.retrieved_lessons,
            )
            if not schema.usable():
                raise DataInputError("No usable measurement columns remain after cleaning.")
            from pramana.verification.stats.effect_size import MAX_SENS_SLOPE_OBSERVATIONS

            if len(prepared.dataset) > MAX_SENS_SLOPE_OBSERVATIONS and any(
                item.is_time_like and item.usable_for_hypotheses for item in schema.columns.values()
            ):
                raise DataInputError(
                    f"Trend analysis supports at most {MAX_SENS_SLOPE_OBSERVATIONS} rows. "
                    "Upload a smaller, deliberately selected table; no rows were silently sampled."
                )
            return result

        def analyze(current: PramanaState) -> Any:
            self.repository.progress(run_id, "Proposing candidate claims")
            return adapters.analyze(current)

        def write(current: PramanaState, proofs: Sequence[ProofObject]) -> Any:
            self.repository.progress(run_id, "Writing verified memory")
            return memory_write(current, proofs)

        selected = replace(
            adapters, ingest=ingest, subagents=prepare, analyze=analyze, memory_write=write
        )
        return run_graph(state, build_graph(selected))

    @staticmethod
    def _chart(candidate: Any, state: PramanaState) -> Any:
        """Draw a claim's data; a charting problem must never fail or alter a verified run."""
        try:
            return claim_chart(candidate, state.dataset)
        except Exception as error:
            get_logger(component="api", run_id=str(state.run_id)).warning(
                "chart_failed", error_type=type(error).__name__
            )
            return None

    def _advisory(
        self, state: PramanaState, rows: list[ResultRow], candidates: dict[str, Any]
    ) -> AdvisoryReport | None:
        """Summaries and confound caveats for PASS findings, or None. Never touches a verdict.

        Runs after every proof exists (and after memory was written inside the graph), reads
        copies of the numbers, and any failure leaves the results exactly as they were.
        """
        try:
            from pramana.verification.config import load_config as load_verification_config

            findings = []
            alpha = load_verification_config().statistics.alpha
            for row in rows:
                proof, candidate = row.proof, candidates[row.insight_id]
                if proof.verdict is not Verdict.PASS:
                    continue
                findings.append(
                    Finding(
                        insight_id=row.insight_id,
                        claim=row.claim,
                        claim_type=str(candidate.claim_type),
                        variables=tuple(candidate.variables),
                        direction=str(candidate.asserted_direction)
                        if candidate.asserted_direction
                        else None,
                        reference_group=candidate.reference_group,
                        q_value=proof.q_value,
                        p_value=proof.p_value,
                        effect_size=proof.effect_size,
                        effect_metric=proof.effect_metric.value if proof.effect_metric else None,
                        band=row.effect_strength,
                        n=row.complete_rows,
                        family_size=proof.n_hypotheses_in_batch,
                        alpha=alpha,
                    )
                )
            if not findings or not hasattr(state.dataset, "columns"):
                return None
            return advise(
                findings,
                state.dataset,
                SchemaProfile.model_validate(state.schema_profile),
                run_id=state.run_id,
                chat=self._advisory_chat,
            )
        except Exception as error:
            get_logger(component="api", run_id=str(state.run_id)).warning(
                "advisory_failed", error_type=type(error).__name__
            )
            return None

    @staticmethod
    def _exploration(state: PramanaState) -> ExplorationSummary | None:
        """What the analyst looked at, with how many claims the gateway actually tested."""
        if not state.exploration:
            return None
        summary = ExplorationSummary.model_validate(state.exploration)
        tested = state.verification_summary.n_tested if state.verification_summary else 0
        return summary.model_copy(
            update={"proposed": len(state.candidate_insights), "tested": tested}
        )

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
                    ResultRow(
                        insight_id=proof.insight_id,
                        claim=candidate.claim,
                        proof=proof,
                        explanation=rejection_reason(proof),
                        effect_strength=effect_strength(proof),
                        n_permutations=permutation_count(proof),
                        chart=self._chart(candidate, state),
                        complete_rows=(
                            int(state.dataset.dropna(subset=candidate.variables).shape[0])
                            if hasattr(state.dataset, "dropna")
                            else None
                        ),
                    )
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
                exploration=self._exploration(state),
                advisory=self._advisory(state, rows, candidates),
            )
            error = (
                "Some workflow steps failed; inspect the local run logs." if state.errors else None
            )
            if state.verification_summary and state.verification_summary.generator_unavailable:
                error = (
                    "Verification generator unavailable. Check DeepSeek credentials and Langfuse."
                )
            elif state.errors:
                for failure in state.errors:
                    if failure.error_type == "DataInputError":
                        error = failure.message
                    elif failure.node == "analysis" and failure.error_type == "ProposerUnavailable":
                        error = (
                            f"Analysis model unavailable: {failure.message.rstrip('.')}. "
                            "Check DEEPSEEK_API_KEY and Langfuse configuration; "
                            "no unverified findings were published."
                        )
                    elif failure.node == "ingest":
                        error = (
                            "The file could not be read as a table. "
                            "Check its format, encoding and row limit."
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
