"""The status endpoint tells the UI what can run and what is missing, never a secret value."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pramana.api.main import create_app
from tests.unit.api.test_api import service_for, sign_in


def _status(tmp_path: Path) -> dict:
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        assert client.get("/api/system").status_code == 401
        sign_in(client)
        return client.get("/api/system").json()


def test_offline_profile_needs_no_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRAMANA_ANALYSIS_ENGINE", "deterministic")
    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "template")
    status = _status(tmp_path)
    assert status["analysis_engine"] == "deterministic" and status["model"] is None
    assert status["blockers"] == [] and status["model_ready"] is False
    assert status["budgets"]["max_total_tokens"] > 0
    assert 0 < status["alpha"] < 1


def test_model_engines_name_exactly_what_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRAMANA_ANALYSIS_ENGINE", "agent")
    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "template")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-secret-value")
    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    status = _status(tmp_path)
    assert status["analysis_engine"] == "agent" and status["model_ready"] is False
    assert status["blockers"] == ["Langfuse keys are not set (model calls must be traced)"]
    assert "sk-secret-value" not in str(status)

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    ready = _status(tmp_path / "again")
    assert ready["model_ready"] is True and ready["blockers"] == []


def test_chat_readiness_names_what_is_missing_without_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRAMANA_ANALYSIS_ENGINE", "deterministic")
    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "template")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    status = _status(tmp_path)
    assert status["chat_ready"] is False
    assert status["chat_blockers"] == [
        "DEEPSEEK_API_KEY is not set",
        "Langfuse keys are not set (model calls must be traced)",
    ]
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-secret-value")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    ready = _status(tmp_path / "again")
    assert ready["chat_ready"] is True and ready["chat_blockers"] == []
    assert "sk-secret-value" not in str(ready)
