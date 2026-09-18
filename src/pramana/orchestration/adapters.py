"""Thin, injectable boundaries between the graph and teammate-owned modules."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pramana.common.logging import get_logger
from pramana.contracts import ProofObject, Verdict
from pramana.orchestration.state import PramanaState

NodeUpdate = Mapping[str, Any]
StateAdapter = Callable[[PramanaState], NodeUpdate]
MemoryAdapter = Callable[[PramanaState, Sequence[ProofObject]], NodeUpdate]


class IntegrationDependencyError(RuntimeError):
    """Raised when a teammate-owned public interface is not available yet."""


class RetryableWorkflowError(RuntimeError):
    """An infrastructure failure that may safely repeat the same graph node."""


def _stub_ingest(state: PramanaState) -> NodeUpdate:
    return {"dataset": state.dataset}


def _stub_subagents(state: PramanaState) -> NodeUpdate:
    return {"schema_profile": state.schema_profile}


def _stub_analysis(state: PramanaState) -> NodeUpdate:
    return {"candidate_insights": []}


def _stub_verification(state: PramanaState) -> NodeUpdate:
    if state.candidate_insights:
        raise IntegrationDependencyError(
            "The verification gateway is unavailable; refusing candidate insights"
        )
    return {"proof_objects": []}


def _stub_memory(state: PramanaState, proofs: Sequence[ProofObject]) -> NodeUpdate:
    if proofs:
        raise IntegrationDependencyError(
            "The verified-memory interface is unavailable; refusing proof writes"
        )
    return {"memory_receipts": []}


def safe_report_adapter(state: PramanaState) -> NodeUpdate:
    """Build a report containing only original claims with gateway-issued PASS proofs."""
    candidates = {candidate.insight_id: candidate for candidate in state.candidate_insights}
    error_rows = [error.model_dump(mode="json") for error in state.errors]
    return {
        "report": {
            "run_id": str(state.run_id),
            "status": state.status.value,
            "insights": [
                {
                    "insight_id": proof.insight_id,
                    "claim": candidates[proof.insight_id].claim,
                    "proof": proof,
                }
                for proof in state.proof_objects
                if proof.verdict is Verdict.PASS and proof.insight_id in candidates
            ],
            "errors": error_rows,
        }
    }


@dataclass(frozen=True)
class WorkflowAdapters:
    """Public module callables consumed by graph nodes."""

    ingest: StateAdapter
    subagents: StateAdapter
    analyze: StateAdapter
    verify: StateAdapter
    memory_write: MemoryAdapter
    report: StateAdapter
    is_stub: bool = False


def stub_adapters() -> WorkflowAdapters:
    """Return fail-closed adapters for skeleton runs before teammate APIs land."""
    return WorkflowAdapters(
        ingest=_stub_ingest,
        subagents=_stub_subagents,
        analyze=_stub_analysis,
        verify=_stub_verification,
        memory_write=_stub_memory,
        report=safe_report_adapter,
        is_stub=True,
    )


def _serializable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def inprocess_verification_adapter(state: PramanaState) -> NodeUpdate:
    """Verify the complete candidate family in this process, with no queue involved.

    For local and demo runs without Redis or a Celery worker. The gateway still runs
    each falsification program in its own sandboxed subprocess; only the dispatch
    changes. It receives the in-memory cleaned frame the candidates were generated
    from, so no ``dataset_ref`` resolution is needed.
    """
    from pramana.verification.config import load_config as load_verification_config
    from pramana.verification.gateway import verify_batch

    if not state.candidate_insights:
        return {"proof_objects": []}
    if state.dataset is None:
        raise ValueError("In-process verification requires the cleaned dataset in state")
    proofs = verify_batch(state.candidate_insights, state.dataset, load_verification_config())
    return {"proof_objects": proofs}


def celery_verification_adapter(state: PramanaState) -> NodeUpdate:
    """Execute the full candidate family through the configured Celery gateway task."""
    from celery.exceptions import (
        SoftTimeLimitExceeded,
        TaskRevokedError,
        TimeLimitExceeded,
        WorkerLostError,
    )
    from celery.exceptions import (
        TimeoutError as CeleryTimeoutError,
    )
    from kombu.exceptions import OperationalError

    from pramana.orchestration.tasks import enqueue_verification

    if not state.candidate_insights:
        return {"proof_objects": []}
    if not state.dataset_ref:
        raise ValueError("dataset_ref is required for queued verification")
    candidates = [_serializable(candidate) for candidate in state.candidate_insights]
    try:
        async_result = enqueue_verification(str(state.run_id), candidates, state.dataset_ref)
    except OperationalError as error:
        raise RetryableWorkflowError("Verification queue is unavailable") from error
    try:
        result = async_result.get(timeout=state.runtime.queue.result_timeout_seconds)
    except (CeleryTimeoutError, SoftTimeLimitExceeded, TimeLimitExceeded) as error:
        try:
            async_result.revoke(terminate=True)
        except OperationalError:
            get_logger(component="verification-adapter", run_id=str(state.run_id)).warning(
                "verification_revoke_failed"
            )
        raise RetryableWorkflowError(
            "Verification task exceeded the configured queue timeout"
        ) from error
    except (OperationalError, TaskRevokedError, WorkerLostError) as error:
        raise RetryableWorkflowError("Verification worker did not complete the task") from error
    if not isinstance(result, Mapping):
        raise ValueError("Verification task returned a non-mapping result")
    return result
