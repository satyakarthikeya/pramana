import pytest

from pramana.orchestration.graph import run_stub_graph
from pramana.orchestration.run_lifecycle import new_run
from pramana.orchestration.state import RunStatus


@pytest.mark.integration
def test_safe_skeleton_runs_end_to_end_without_exposing_insights() -> None:
    final = run_stub_graph(new_run(dataset_ref="toy.csv"))
    assert final.status == RunStatus.COMPLETED
    assert "verification" in final.visited_nodes
    assert final.report is not None
    assert final.report["status"] == "completed"
    assert final.report["insights"] == []
    assert final.memory_receipts == []
