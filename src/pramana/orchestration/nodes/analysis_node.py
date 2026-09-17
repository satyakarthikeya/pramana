"""Candidate-insight analysis graph node."""

from typing import Any

from pramana.orchestration.adapters import StateAdapter
from pramana.orchestration.state import PramanaState


def analysis_node(state: PramanaState, adapter: StateAdapter) -> dict[str, Any]:
    """Delegate candidate generation to the analysis module."""
    return {**adapter(state), "visited_nodes": [*state.visited_nodes, "analysis"]}
