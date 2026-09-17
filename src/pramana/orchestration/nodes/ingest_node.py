"""Dataset-ingestion graph node."""

from typing import Any

from pramana.orchestration.adapters import StateAdapter
from pramana.orchestration.state import PramanaState


def ingest_node(state: PramanaState, adapter: StateAdapter) -> dict[str, Any]:
    """Delegate ingestion without implementing analysis-owned behavior."""
    return {**adapter(state), "visited_nodes": [*state.visited_nodes, "ingest"]}
