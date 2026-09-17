import pytest

from pramana.orchestration.run_lifecycle import (
    complete_run,
    record_failure,
    start_run,
    transition,
)
from pramana.orchestration.state import RunStatus
from tests.unit.orchestration.helpers import make_run


def test_new_run_has_unique_id_and_valid_config() -> None:
    first = make_run("data/example.csv", user_query="Find trends")
    second = make_run("data/example.csv")
    assert first.run_id != second.run_id
    assert first.status == RunStatus.PENDING
    assert first.dataset_ref == "data/example.csv"
    assert first.user_query == "Find trends"


def test_lifecycle_rejects_invalid_transition() -> None:
    with pytest.raises(ValueError):
        transition(make_run(), RunStatus.COMPLETED)


def test_exhausted_failure_is_degraded_and_cannot_complete() -> None:
    state = start_run(make_run())
    state = record_failure(state, "verification", RuntimeError("boom"), 3, exhausted=True)
    assert state.status == RunStatus.DEGRADED
    assert complete_run(state).status == RunStatus.DEGRADED
    assert state.errors[-1].node == "verification"
    assert state.retry_counts["verification"] == 2
