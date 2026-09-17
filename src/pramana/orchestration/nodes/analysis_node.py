"""Candidate-insight analysis graph node."""

from typing import Any

from pramana.contracts import CandidateInsight
from pramana.orchestration.adapters import StateAdapter
from pramana.orchestration.state import PramanaState


def analysis_node(state: PramanaState, adapter: StateAdapter) -> dict[str, Any]:
    """Accept only unique contract-valid candidates tied to the active dataset."""
    update = dict(adapter(state))
    raw_candidates = update.get("candidate_insights", [])
    candidates = [
        item if isinstance(item, CandidateInsight) else CandidateInsight.model_validate(item)
        for item in raw_candidates
    ]
    identifiers = [candidate.insight_id for candidate in candidates]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Analysis must emit unique insight_id values within a run")
    if state.dataset_ref is not None:
        mismatched = [
            candidate.insight_id
            for candidate in candidates
            if candidate.dataset_ref != state.dataset_ref
        ]
        if mismatched:
            raise ValueError(
                "Analysis candidates must reference the exact cleaned dataset; "
                f"mismatched insight IDs: {mismatched}"
            )
    update["candidate_insights"] = candidates
    update["visited_nodes"] = [*state.visited_nodes, "analysis"]
    return update
