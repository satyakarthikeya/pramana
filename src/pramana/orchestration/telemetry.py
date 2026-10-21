"""Export bounded worker-result telemetry from the trusted graph process only."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from pramana.common.logging import get_logger
from pramana.contracts import ProofObject
from pramana.verification.gateway import BatchSummary

_MAX_INSIGHT_ROWS = 50
_MAX_IDENTIFIER_LENGTH = 128


def relay_verification_result(
    client: Any | None,
    run_id: UUID,
    summary: BatchSummary,
    proofs: Sequence[ProofObject],
) -> bool:
    """Relay bounded completion metadata without source, prompts, rows or error text.

    The existing Celery result carries diagnostics to the trusted graph; no worker
    egress or new worker ingress is required. This is completion telemetry, not
    replay of every executor log. A killed worker has no completion observation;
    its caller's workflow failure remains the corresponding failure observation.
    Telemetry failure cannot change a proof or trigger re-execution.
    """
    observe = getattr(client, "start_as_current_observation", None)
    if observe is None:
        return False
    metadata = {
        "run_id": str(run_id),
        "generator": summary.generator,
        "n_candidates": summary.n_candidates,
        "n_tested": summary.n_tested,
        "n_screened_out": summary.n_screened_out,
        "generator_unavailable_count": summary.generator_unavailable_count,
        "n_template_comparisons": summary.n_template_comparisons,
        "n_template_disagreements": len(summary.template_disagreements),
        "n_template_unavailable": summary.n_template_unavailable,
        "truncated_insight_count": max(0, len(proofs) - _MAX_INSIGHT_ROWS),
        "insights": [
            {
                "insight_id": proof.insight_id[:_MAX_IDENTIFIER_LENGTH],
                "verdict": proof.verdict.value,
                "gate_outcome": proof.gate_outcome.value,
                "execution_failed": proof.failure_reason is not None,
            }
            for proof in proofs[:_MAX_INSIGHT_ROWS]
        ],
    }
    try:
        with observe(
            name="verification-result-relay",
            as_type="span",
            trace_context={"trace_id": run_id.hex},
            metadata=metadata,
        ):
            pass
    except Exception:
        get_logger(component="telemetry", run_id=str(run_id)).warning(
            "verification_telemetry_relay_failed"
        )
        return False
    return True
