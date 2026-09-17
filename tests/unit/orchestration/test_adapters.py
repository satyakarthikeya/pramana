from typing import Any

import pytest
from celery.exceptions import TimeoutError as CeleryTimeoutError

from pramana.orchestration.adapters import RetryableWorkflowError, celery_verification_adapter
from pramana.orchestration.run_lifecycle import new_run
from tests.unit.orchestration.helpers import candidate


class FakeAsyncResult:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.timeout: int | None = None
        self.revoked = False

    def get(self, timeout: int) -> Any:
        self.timeout = timeout
        if self.error is not None:
            raise self.error
        return self.result

    def revoke(self, terminate: bool) -> None:
        self.revoked = terminate


def test_celery_adapter_dispatches_complete_family(monkeypatch: pytest.MonkeyPatch) -> None:
    state = new_run("toy.csv")
    state.candidate_insights = [candidate("a"), candidate("b")]
    result = FakeAsyncResult({"proof_objects": []})
    captured: dict[str, Any] = {}

    def enqueue(run_id: str, candidates: list[dict[str, Any]], dataset_ref: str) -> Any:
        captured.update(run_id=run_id, candidates=candidates, dataset_ref=dataset_ref)
        return result

    monkeypatch.setattr("pramana.orchestration.tasks.enqueue_verification", enqueue)
    assert celery_verification_adapter(state) == {"proof_objects": []}
    assert [item["insight_id"] for item in captured["candidates"]] == ["a", "b"]
    assert result.timeout == state.runtime.queue.result_timeout_seconds


def test_celery_adapter_revokes_timeout_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    state = new_run("toy.csv")
    result = FakeAsyncResult(error=CeleryTimeoutError())
    monkeypatch.setattr(
        "pramana.orchestration.tasks.enqueue_verification",
        lambda *_args: result,
    )
    with pytest.raises(RetryableWorkflowError):
        celery_verification_adapter(state)
    assert result.revoked is True


def test_celery_adapter_requires_dataset_reference() -> None:
    with pytest.raises(ValueError, match="dataset_ref"):
        celery_verification_adapter(new_run())
