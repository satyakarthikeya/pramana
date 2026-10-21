"""Provider constraints and tracing failures never send keys or imply verified data."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from structlog.contextvars import bound_contextvars, clear_contextvars

from pramana.common import llm_client
from pramana.verification.falsification import generator
from tests.fixtures.config import load_pinned_config


@pytest.mark.parametrize(
    "url",
    [
        "http://api.deepseek.com",
        "https://api.deepseek.com.evil.example",
        "https://user:pw@api.deepseek.com",
        "https://api.deepseek.com?key=x",
        "https://api.deepseek.com:444",
        "https://openrouter.ai/api/v1",
    ],
)
def test_wrong_endpoint_refused_before_transport(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", url)
    call = MagicMock()
    monkeypatch.setattr(generator, "complete_chat", call)
    with bound_contextvars(run_id=str(uuid4())), pytest.raises(generator.GeneratorUnavailable):
        generator._call_deepseek("system", "user", load_pinned_config())
    call.assert_not_called()


def test_missing_run_id_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret")
    clear_contextvars()
    call = MagicMock()
    monkeypatch.setattr(generator, "complete_chat", call)
    with pytest.raises(generator.GeneratorUnavailable):
        generator._call_deepseek("system", "user", load_pinned_config())
    call.assert_not_called()


def test_missing_tracing_never_calls_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret")
    monkeypatch.setattr(llm_client, "get_langfuse_client", lambda _: None)
    call = MagicMock()
    monkeypatch.setattr(llm_client, "_request", call)
    with bound_contextvars(run_id=str(uuid4())), pytest.raises(generator.GeneratorUnavailable):
        generator._call_deepseek("system", "user", load_pinned_config())
    call.assert_not_called()
