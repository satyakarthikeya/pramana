"""Routine Gemma/schema/cleaning orchestration node."""

from typing import Any

from pramana.orchestration.adapters import StateAdapter
from pramana.orchestration.state import PramanaState


def subagents_node(state: PramanaState, adapter: StateAdapter) -> dict[str, Any]:
    """Invoke the analysis-owned preparation adapter and record graph progress."""
    return {**adapter(state), "visited_nodes": [*state.visited_nodes, "subagents"]}
