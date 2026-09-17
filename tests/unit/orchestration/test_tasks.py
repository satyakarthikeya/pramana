from typing import Any

import pytest

from pramana.orchestration import tasks
from pramana.orchestration.adapters import IntegrationDependencyError


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
