"""Mandatory verification-gateway graph node."""

from typing import Any

from pramana.contracts import ProofObject
from pramana.orchestration.adapters import StateAdapter
from pramana.orchestration.state import PramanaState


def _insight_id(value: Any) -> str | None:
    identifier = (
        value.get("insight_id") if isinstance(value, dict) else getattr(value, "insight_id", None)
    )
    return str(identifier) if identifier is not None else None


def verification_node(state: PramanaState, adapter: StateAdapter) -> dict[str, Any]:
    """Verify the complete candidate family and require one proof per candidate."""
    candidate_ids = [_insight_id(item) for item in state.candidate_insights]
    if any(identifier is None for identifier in candidate_ids):
        raise ValueError("Every candidate insight must carry insight_id")
    normalized_candidates = [str(identifier) for identifier in candidate_ids]
    if len(set(normalized_candidates)) != len(normalized_candidates):
        raise ValueError("Candidate insight IDs must be unique within a run")

    update = dict(adapter(state))
    proofs = [
        proof if isinstance(proof, ProofObject) else ProofObject.model_validate(proof)
        for proof in update.get("proof_objects", [])
    ]
    proof_ids = [_insight_id(item) for item in proofs]
    if any(identifier is None for identifier in proof_ids):
        raise ValueError("Every proof object must carry insight_id")
    normalized_proofs = [str(identifier) for identifier in proof_ids]
    if len(set(normalized_proofs)) != len(normalized_proofs):
        raise ValueError("Verification must not emit duplicate proof objects")
    if sorted(normalized_candidates) != sorted(normalized_proofs):
        raise ValueError("Verification must emit exactly one proof object per candidate")
    update["proof_objects"] = proofs
    update["visited_nodes"] = [*state.visited_nodes, "verification"]
    return update
