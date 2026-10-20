"""Hosted-Gemma proposer: same guardrails as the local one, plus key and endpoint rules."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pramana.analysis.config import load_config
from pramana.analysis.hypotheses import llm_proposer as proposer
from pramana.analysis.hypotheses.generation import generate_candidates
from pramana.analysis.proposer_config import ProposerSettings
from pramana.analysis.schema_inference import infer_schema
from tests.fixtures.frames import toy_frame


@pytest.fixture
def inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    monkeypatch.setattr(proposer, "DATA_DIR", tmp_path)
    monkeypatch.setenv("PRAMANA_ANALYSIS_API_KEY", "test-key")
    config = load_config()
    hypothesis = config.hypotheses.model_copy(
        update={
            "proposer": config.hypotheses.proposer.model_copy(
                update={"engine": "api", "trace_backend": "local"}
            )
        }
    )
    frame = toy_frame()
    return frame, infer_schema(frame, config.schema_inference), hypothesis


def fake_openai(monkeypatch: pytest.MonkeyPatch, content: str, finish: str = "stop") -> MagicMock:
    create = MagicMock(
        return_value=SimpleNamespace(
            model="provider-alias",
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            choices=[
                SimpleNamespace(
                    finish_reason=finish, message=SimpleNamespace(content=content)
                )
            ],
        )
    )
    factory = MagicMock(
        return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    )
    import openai

    monkeypatch.setattr(openai, "OpenAI", factory)
    factory.create = create
    return factory


def batch(**changes: Any) -> str:
    claim = {
        "claim_type": "correlation",
        "variables": ["age", "bmi"],
        "direction": "positive",
        "reference_group": None,
        **changes,
    }
    return json.dumps({"claims": [claim]})


@pytest.mark.parametrize(
    "patch",
    [
        {"api_base_url": "http://openrouter.ai/api/v1"},
        {"api_base_url": "https://user:pw@openrouter.ai/api/v1"},
        {"api_base_url": "https://openrouter.ai/api/v1?key=x"},
        {"api_model": "deepseek-v4"},
        {"api_model": "google/not-gemma"},
        {"api_key_env": "not a name"},
    ],
)
def test_unsafe_api_settings_are_refused(patch: dict) -> None:
    raw = load_config().hypotheses.proposer.model_dump() | patch
    with pytest.raises(ValidationError):
        ProposerSettings.model_validate(raw)


def test_api_proposal_becomes_a_code_rendered_candidate(
    inputs: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame, schema, config = inputs
    factory = fake_openai(monkeypatch, batch())
    candidates = generate_candidates(frame, schema, config, dataset_ref="c.pkl", run_id=uuid4())
    assert [c.claim for c in candidates] == ["bmi is positively associated with age"]
    kwargs = factory.call_args.kwargs
    assert kwargs["api_key"] == "test-key"
    assert kwargs["base_url"] == config.proposer.api_base_url
    assert kwargs["max_retries"] == 0
    sent = factory.create.call_args.kwargs
    assert sent["model"] == config.proposer.api_model
    assert "SECRET" not in sent["messages"][0]["content"]


def test_missing_key_fails_closed_without_a_request(
    inputs: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame, schema, config = inputs
    monkeypatch.delenv("PRAMANA_ANALYSIS_API_KEY")
    factory = fake_openai(monkeypatch, batch())
    with pytest.raises(proposer.ProposerUnavailable):
        generate_candidates(frame, schema, config, dataset_ref="c.pkl", run_id=uuid4())
    factory.assert_not_called()


@pytest.mark.parametrize(
    ("content", "finish"),
    [
        (batch(), "length"),
        ("not json", "stop"),
        (batch(p_value=0.001), "stop"),
        (batch(claim="bmi always raises age"), "stop"),
    ],
)
def test_truncated_malformed_or_overreaching_output_is_refused(
    inputs: tuple, monkeypatch: pytest.MonkeyPatch, content: str, finish: str
) -> None:
    frame, schema, config = inputs
    fake_openai(monkeypatch, content, finish)
    with pytest.raises(proposer.ProposerUnavailable):
        generate_candidates(frame, schema, config, dataset_ref="c.pkl", run_id=uuid4())


def test_same_run_replays_the_recorded_response(
    inputs: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame, schema, config = inputs
    factory = fake_openai(monkeypatch, batch())
    run_id = uuid4()
    first = generate_candidates(frame, schema, config, dataset_ref="c.pkl", run_id=run_id)
    second = generate_candidates(frame, schema, config, dataset_ref="c.pkl", run_id=run_id)
    assert first == second
    assert factory.create.call_count == 1
