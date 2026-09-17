from typing import Any

import pytest

from pramana.orchestration import tasks
from pramana.orchestration.adapters import IntegrationDependencyError
from tests.unit.orchestration.helpers import proof


def test_task_fails_closed_without_registered_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "_handler", None)
    monkeypatch.delenv("PRAMANA_VERIFICATION_HANDLER", raising=False)
    with pytest.raises(IntegrationDependencyError):
        tasks.verify_batch_task.run("run-1", [], "toy")


def test_task_requires_proof_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "_handler", lambda _request: {})
    with pytest.raises(ValueError, match="proof_objects"):
        tasks.verify_batch_task.run("run-1", [], "toy")


def test_task_passes_whole_family_to_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def handler(request: dict[str, Any]) -> dict[str, Any]:
        seen.update(request)
        return {"proof_objects": []}

    monkeypatch.setattr(tasks, "_handler", handler)
    result = tasks.verify_batch_task.run("run-1", [{"insight_id": "a"}, {"insight_id": "b"}], "toy")
    assert [item["insight_id"] for item in seen["candidate_insights"]] == ["a", "b"]
    assert result == {"proof_objects": []}


def test_task_validates_and_serializes_proof_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tasks,
        "_handler",
        lambda _request: {"proof_objects": [proof("finding", passed=True)]},
    )
    result = tasks.verify_batch_task.run("run-1", [], "toy")
    assert result["proof_objects"][0]["insight_id"] == "finding"
    assert result["proof_objects"][0]["verdict"] == "PASS"


def test_task_relies_on_graph_retry_instead_of_late_acknowledgement() -> None:
    assert tasks.verify_batch_task.acks_late is False


def test_worker_timeout_covers_executor_timeout() -> None:
    tasks.validate_worker_timeouts()


def test_worker_refuses_soft_limit_that_cannot_cover_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pramana.verification.config import load_config as load_verification_config

    executor_timeout = load_verification_config().executor.timeout_seconds
    bad_queue = tasks._runtime.queue.model_copy(
        update={
            "task_soft_time_limit": executor_timeout,
            "task_hard_time_limit": executor_timeout + 5,
            "result_timeout_seconds": executor_timeout + 10,
        }
    )
    monkeypatch.setattr(tasks, "_runtime", tasks._runtime.model_copy(update={"queue": bad_queue}))
    with pytest.raises(RuntimeError, match="must exceed"):
        tasks.validate_worker_timeouts()


def test_worker_logging_uses_runtime_level(monkeypatch: pytest.MonkeyPatch) -> None:
    levels: list[str] = []
    monkeypatch.setattr(tasks, "configure_logging", levels.append)
    tasks.configure_worker_logging()
    assert levels == [tasks._runtime.logging.level]
