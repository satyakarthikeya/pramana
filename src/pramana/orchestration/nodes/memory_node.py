"""Verified-memory graph node."""

from pramana.contracts import Verdict
from pramana.orchestration.adapters import MemoryAdapter
from pramana.orchestration.state import PramanaState


def memory_node(state: PramanaState, adapter: MemoryAdapter) -> dict[str, object]:
    """Send only explicit PASS proof objects to the guarded memory adapter."""
    passed = [proof for proof in state.proof_objects if proof.verdict is Verdict.PASS]
    update = dict(adapter(state, passed))
    update["visited_nodes"] = [*state.visited_nodes, "memory"]
    return update
