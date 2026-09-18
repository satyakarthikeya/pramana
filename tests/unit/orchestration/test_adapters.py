from typing import Any

import pytest
from celery.exceptions import TimeoutError as CeleryTimeoutError

from pramana.orchestration.adapters import RetryableWorkflowError, celery_verification_adapter
from tests.unit.orchestration.helpers import candidate, make_run


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
    state = make_run("toy.csv")
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
    state = make_run("toy.csv")
    state.candidate_insights = [candidate("a")]
    result = FakeAsyncResult(error=CeleryTimeoutError())
    monkeypatch.setattr(
        "pramana.orchestration.tasks.enqueue_verification",
        lambda *_args: result,
    )
    with pytest.raises(RetryableWorkflowError):
        celery_verification_adapter(state)
    assert result.revoked is True


def test_celery_adapter_requires_dataset_reference() -> None:
    state = make_run()
    state.candidate_insights = [candidate("a")]
    with pytest.raises(ValueError, match="dataset_ref"):
        celery_verification_adapter(state)


def test_celery_adapter_short_circuits_empty_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pramana.orchestration.tasks.enqueue_verification",
        lambda *_args: pytest.fail("an empty family must not be queued"),
    )
    assert celery_verification_adapter(make_run()) == {"proof_objects": []}


def test_inprocess_adapter_passes_the_whole_family_and_state_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pramana.verification.gateway as gateway
    from pramana.orchestration.adapters import inprocess_verification_adapter
    from tests.unit.orchestration.helpers import proof

    state = make_run("toy.csv")
    state.dataset = {"frame": "sentinel"}
    state.candidate_insights = [candidate("a"), candidate("b")]
    seen: dict[str, Any] = {}

    def fake_verify_batch(candidates: Any, frame: Any, config: Any) -> list[Any]:
        seen.update(ids=[item.insight_id for item in candidates], frame=frame)
        return [proof("a", passed=True), proof("b", passed=False)]

    monkeypatch.setattr(gateway, "verify_batch", fake_verify_batch)
    result = inprocess_verification_adapter(state)

    assert seen == {"ids": ["a", "b"], "frame": {"frame": "sentinel"}}
    assert [item.insight_id for item in result["proof_objects"]] == ["a", "b"]


def test_inprocess_adapter_short_circuits_empty_family_and_requires_a_frame() -> None:
    from pramana.orchestration.adapters import inprocess_verification_adapter

    assert inprocess_verification_adapter(make_run("toy.csv")) == {"proof_objects": []}
    state = make_run("toy.csv")
    state.candidate_insights = [candidate("a")]
    with pytest.raises(ValueError, match="cleaned dataset"):
        inprocess_verification_adapter(state)
