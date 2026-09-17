"""User-facing report graph node."""

from collections.abc import Mapping
from typing import Any

from pramana.contracts import ProofObject, Verdict
from pramana.orchestration.adapters import StateAdapter
from pramana.orchestration.state import PramanaState


def report_node(state: PramanaState, adapter: StateAdapter) -> dict[str, Any]:
    """Expose only claims paired with their exact gateway-issued PASS proof."""
    update = dict(adapter(state))
    report = update.get("report")
    if report is not None:
        if not isinstance(report, Mapping):
            raise ValueError("Report output must be a mapping")
        insights = report.get("insights", [])
        if not isinstance(insights, list):
            raise ValueError("Report insights must be a list")
        verified = {
            proof.insight_id: proof
            for proof in state.proof_objects
            if proof.verdict is Verdict.PASS
        }
        candidates = {candidate.insight_id: candidate for candidate in state.candidate_insights}
        for item in insights:
            if not isinstance(item, Mapping):
                raise ValueError("Every reported insight must be a mapping")
            raw_proof = item.get("proof")
            try:
                proof = (
                    raw_proof
                    if isinstance(raw_proof, ProofObject)
                    else ProofObject.model_validate(raw_proof)
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "A report may expose only insights carrying a gateway-issued PASS proof"
                ) from error
            issued = verified.get(proof.insight_id)
            candidate = candidates.get(proof.insight_id)
            if (
                item.get("insight_id") != proof.insight_id
                or issued != proof
                or candidate is None
                or item.get("claim") != candidate.claim
            ):
                raise ValueError(
                    "A report may expose only the original claim and its exact gateway-issued "
                    "PASS proof"
                )
    update["visited_nodes"] = [*state.visited_nodes, "report"]
    return update
