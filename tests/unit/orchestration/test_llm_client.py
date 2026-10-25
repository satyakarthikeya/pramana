"""Shared inference budgets, tracing, usage and refusal behavior need no API keys."""

from contextlib import contextmanager
from typing import Any
from urllib.error import HTTPError, URLError
from uuid import uuid4

import pytest

from pramana.common import llm_client as llm


def settings(**overrides: Any) -> llm.LLMSettings:
    return llm.LLMSettings.model_validate(
        {
            "base_url": "https://provider.invalid/v1",
            "model": "explicit-model",
            "api_key": "unit-test-not-a-key",
            "retry_delay_seconds": 0,
            **overrides,
        }
    )


@pytest.fixture
def tracing(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []

    class Span:
        def update(self, **values: Any) -> None:
            observations[-1]["result"] = values

    class Client:
        def auth_check(self) -> bool:
            return True

        @contextmanager
        def start_as_current_observation(self, **values: Any) -> Any:
            observations.append(values)
            yield Span()

    monkeypatch.setattr(llm, "get_langfuse_client", lambda _: Client())
    return observations


def response() -> dict[str, Any]:
    return {
        "model": "explicit-model",
        "choices": [{"finish_reason": "stop", "message": {"content": "structured model text"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }


def test_completion_records_usage_cost_and_uuid_trace(
    monkeypatch: pytest.MonkeyPatch,
    tracing: list[dict[str, Any]],
) -> None:
    monkeypatch.setattr(llm, "_request", lambda *_: response())
    run_id = uuid4()
    result = llm.complete_chat(
        settings(input_usd_per_million=1, output_usd_per_million=2),
        [llm.ChatMessage(role="user", content="schema summary")],
        run_id=run_id,
        insight_id="claim-1",
    )
    assert result.estimated_cost_usd == pytest.approx(0.00014)
    assert result.input_tokens == 100 and result.output_tokens == 20
    assert tracing[0]["trace_context"] == {"trace_id": run_id.hex}
    assert tracing[0]["metadata"]["insight_id"] == "claim-1"
    assert tracing[0]["result"]["output"] == result.content


def test_no_tracing_means_no_model_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "get_langfuse_client", lambda _: None)
    monkeypatch.setattr(llm, "_request", lambda *_: pytest.fail("Untraced request must not run"))
    with pytest.raises(llm.LLMUnavailable, match="Langfuse"):
        llm.complete_chat(
            settings(), [llm.ChatMessage(role="user", content="test")], run_id=uuid4()
        )


def test_invalid_tracing_auth_prevents_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        def auth_check(self) -> bool:
            return False

    monkeypatch.setattr(llm, "get_langfuse_client", lambda _: Client())
    monkeypatch.setattr(llm, "_request", lambda *_: pytest.fail("Untraced request must not run"))
    with pytest.raises(llm.LLMUnavailable, match="authentication"):
        llm.complete_chat(
            settings(), [llm.ChatMessage(role="user", content="test")], run_id=uuid4()
        )


@pytest.mark.parametrize("status, expected_attempts", [(401, 1), (403, 1), (429, 3), (503, 3)])
def test_only_transient_errors_retry_same_model_with_bounded_attempts(
    status: int,
    expected_attempts: int,
    monkeypatch: pytest.MonkeyPatch,
    tracing: list[dict[str, Any]],
) -> None:
    seen: list[str] = []

    def fail(config: llm.LLMSettings, _payload: bytes) -> Any:
        seen.append(config.model)
        raise HTTPError(config.base_url, status, "secret-provider-error", {}, None)

    monkeypatch.setattr(llm, "_request", fail)
    with pytest.raises(llm.LLMUnavailable) as error:
        llm.complete_chat(
            settings(), [llm.ChatMessage(role="user", content="test")], run_id=uuid4()
        )
    assert seen == ["explicit-model"] * expected_attempts
    assert len(tracing) == expected_attempts
    assert "secret-provider-error" not in str(error.value)


def test_transient_request_can_recover_without_substitution(
    monkeypatch: pytest.MonkeyPatch,
    tracing: list[dict[str, Any]],
) -> None:
    outcomes = iter([URLError("secret-network-error"), response()])

    def request(*_args: Any) -> Any:
        item = next(outcomes)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(llm, "_request", request)
    result = llm.complete_chat(
        settings(), [llm.ChatMessage(role="user", content="test")], run_id=uuid4()
    )
    assert result.content == "structured model text"
    assert result.estimated_cost_usd is None  # Missing prices are not free inference.
    assert len(tracing) == 2


@pytest.mark.parametrize(
    "bad_response",
    [
        {},
        {"choices": []},
        {"choices": [{"finish_reason": "length"}]},
        {"choices": [{"message": {"content": ""}}]},
        {"choices": [{"message": {"content": {"unexpected": "object"}}}]},
    ],
)
def test_malformed_model_output_fails_without_retry(
    bad_response: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tracing: list[dict[str, Any]],
) -> None:
    monkeypatch.setattr(llm, "_request", lambda *_: bad_response)
    with pytest.raises(llm.LLMUnavailable):
        llm.complete_chat(
            settings(), [llm.ChatMessage(role="user", content="test")], run_id=uuid4()
        )
    assert len(tracing) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example/v1",
        "https://user:password@example.com/v1",
        "https://example.com/v1?api_key=secret",
        "file:///tmp/not-an-api",
    ],
)
def test_endpoint_validation_refuses_plaintext_remote_and_embedded_credentials(url: str) -> None:
    with pytest.raises(ValueError):
        settings(base_url=url)


def test_local_ollama_endpoint_is_explicit_and_key_is_redacted() -> None:
    config = settings(base_url="http://localhost:11434/v1")
    assert "unit-test-not-a-key" not in repr(config)
    assert config.base_url.endswith("/v1")
    with pytest.raises(ValueError, match="both token prices"):
        settings(input_usd_per_million=1)


def test_transport_bounds_response_and_passes_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, Any] = {}

    class Response:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, *_args: Any) -> None:
            pass

        def read(self, limit: int) -> bytes:
            observed["limit"] = limit
            return b"x" * limit

    class Opener:
        def open(self, request: Any, timeout: float) -> Any:
            observed.update(url=request.full_url, timeout=timeout)
            return Response()

    monkeypatch.setattr(llm, "build_opener", lambda *_: Opener())
    with pytest.raises(llm.LLMUnavailable, match="byte limit"):
        llm._request(settings(max_response_bytes=1024, timeout_seconds=7), b"{}")
    assert observed == {
        "url": "https://provider.invalid/v1/chat/completions",
        "timeout": 7,
        "limit": 1025,
    }


def test_redirects_are_not_followed_with_authorization() -> None:
    assert llm._NoRedirect().redirect_request(None) is None


def test_a_one_off_auth_failure_is_retried_but_a_persistent_one_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "_AUTH_BACKOFF_SECONDS", 0.0)
    calls = {"n": 0}

    class Flaky:
        def auth_check(self) -> bool:
            calls["n"] += 1
            return calls["n"] >= 2  # the first check fails, the second passes

    monkeypatch.setattr(llm, "get_langfuse_client", lambda _: Flaky())
    assert isinstance(llm._authenticated_langfuse(), Flaky) and calls["n"] == 2

    class Down:
        def auth_check(self) -> bool:
            calls["n"] += 1
            raise OSError("network down")

    calls["n"] = 0
    monkeypatch.setattr(llm, "get_langfuse_client", lambda _: Down())
    with pytest.raises(llm.LLMUnavailable, match="authentication"):
        llm._authenticated_langfuse()
    assert calls["n"] == llm._AUTH_ATTEMPTS
