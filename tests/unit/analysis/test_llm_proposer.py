"""Proposer safety: model selections only, traced calls, bounded context and no fallback."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pandas as pd
import pytest
from pydantic import ValidationError

from pramana.analysis.config import load_config
from pramana.analysis.hypotheses import llm_proposer as proposer
from pramana.analysis.hypotheses.generation import generate_candidates
from pramana.analysis.proposer_config import ProposerSettings
from pramana.analysis.schema_inference import ColumnRole, infer_schema
from pramana.contracts import Direction
from tests.fixtures.frames import toy_frame


@pytest.fixture
def inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    monkeypatch.setattr(proposer, "DATA_DIR", tmp_path)
    config = load_config()
    hypothesis = config.hypotheses.model_copy(
        update={
            "proposer": config.hypotheses.proposer.model_copy(
                update={"engine": "api", "trace_backend": "langfuse"}
            )
        }
    )
    frame = toy_frame()
    schema = infer_schema(frame, config.schema_inference)
    return frame, schema, hypothesis


def claim(**changes: Any) -> dict:
    return {
        "claim_type": "correlation",
        "variables": ["age", "bmi"],
        "direction": "positive",
        "reference_group": None,
        **changes,
    }


def install_fake_model(monkeypatch: pytest.MonkeyPatch, claims: list[dict]) -> tuple:
    observation = MagicMock()
    tracing = MagicMock()
    tracing.auth_check.return_value = True

    @contextmanager
    def generation(**kwargs):
        tracing.start_kwargs = kwargs
        yield observation

    tracing.start_as_current_observation = generation
    monkeypatch.setattr(proposer, "get_langfuse_client", lambda _settings: tracing)
    transport = MagicMock()
    transport.chat.return_value = {
        "model": "deepseek-flash",
        "done": True,
        "done_reason": "stop",
        "message": {"content": json.dumps({"claims": claims})},
        "prompt_eval_count": 100,
        "eval_count": 100,
        "total_duration": 1000,
    }
    factory = MagicMock(return_value=transport)
    monkeypatch.setattr(proposer, "_call_api", lambda *args: transport.chat(*args))
    return tracing, observation, factory, transport


@pytest.mark.parametrize(
    "patch",
    [
        {"base_url": "https://evil.example"},
        {"base_url": "http://localhost:11434/?key=x"},
        {"base_url": "http://user:password@localhost:11434"},
        {"model": "deepseek-v4"},
        {"engine": "unknown"},
        {"model": "gemma2:cloud"},
        {"num_threads": 0},
    ],
)
def test_invalid_model_endpoint_and_resource_settings_are_refused(patch: dict) -> None:
    raw = load_config().hypotheses.proposer.model_dump() | patch
    with pytest.raises(ValidationError):
        ProposerSettings.model_validate(raw)


@pytest.mark.parametrize(
    "forbidden", ["claim", "p_value", "q_value", "verdict", "evidence", "code"]
)
def test_model_cannot_author_claim_text_or_statistics(forbidden: str) -> None:
    with pytest.raises(ValidationError):
        proposer.StructuredClaim.model_validate(claim(**{forbidden: "invented"}))


def test_prompt_excludes_rows_ids_relationships_and_limits_context(inputs: tuple) -> None:
    frame, schema, config = inputs
    frame["patient_id"] = [f"SECRET_PERSON_{index}" for index in range(len(frame))]
    schema = infer_schema(frame, load_config().schema_inference)
    prompt, allowed = proposer.build_prompt(
        frame, schema, config.proposer, user_query="Q" * 2000, lesson_hints=["hint"]
    )
    assert "SECRET_PERSON" not in prompt
    assert "patient_id" not in allowed
    payload = json.loads(prompt.split("INPUT_DATA_JSON:\n")[1])
    assert len(payload["question"]) == config.proposer.max_question_chars
    assert "relationships" not in payload
    assert "correlation_matrix" not in payload
    assert "rows" not in payload
    assert payload["historical_hints"] == "hint"
    assert len(prompt) <= config.proposer.max_prompt_chars
    assert "direction MUST be positive or negative" in prompt
    assert "NEVER null" in prompt


def test_traced_model_batch_replay_and_no_frame_mutation(
    inputs: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame, schema, config = inputs
    before = frame.copy(deep=True)
    tracing, observation, factory, transport = install_fake_model(monkeypatch, [claim()])
    run_id = uuid4()
    candidates = generate_candidates(
        frame, schema, config, dataset_ref="cleaned.pkl", run_id=run_id
    )
    assert len(candidates) == 1
    assert candidates[0].claim == "bmi is positively associated with age"
    assert candidates[0].asserted_direction is Direction.POSITIVE
    assert tracing.start_kwargs["trace_context"]["trace_id"] == run_id.hex
    assert tracing.start_kwargs["model"] == config.proposer.api_model
    assert transport.chat.call_args.args[1].api_model == "deepseek-flash"
    assert transport.chat.call_args.args[2] == run_id
    assert observation.update.called
    assert (
        generate_candidates(frame, schema, config, dataset_ref="cleaned.pkl", run_id=run_id)
        == candidates
    )
    assert transport.chat.call_count == 1
    with pytest.raises(proposer.ProposerUnavailable, match="Recorded"):
        generate_candidates(frame, schema, config, dataset_ref="different.pkl", run_id=run_id)
    pd.testing.assert_frame_equal(before, frame)


def test_missing_tracing_refuses_before_any_api_request(
    inputs: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame, schema, config = inputs
    monkeypatch.setattr(proposer, "get_langfuse_client", lambda _settings: None)
    factory = MagicMock()
    monkeypatch.setattr(proposer, "_call_api", factory)
    with pytest.raises(proposer.ProposerUnavailable, match="Langfuse"):
        generate_candidates(frame, schema, config, dataset_ref="cleaned.pkl", run_id=uuid4())
    factory.assert_not_called()


def test_local_trace_backend_cannot_bypass_remote_tracing(
    inputs: tuple,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    frame, schema, config = inputs
    config = config.model_copy(
        update={"proposer": config.proposer.model_copy(update={"trace_backend": "local"})}
    )
    _, _, _, transport = install_fake_model(monkeypatch, [claim()])
    tracing_factory = MagicMock(side_effect=AssertionError("local mode must not request Langfuse"))
    monkeypatch.setattr(proposer, "get_langfuse_client", tracing_factory)
    run_id = uuid4()
    with pytest.raises(proposer.ProposerUnavailable, match="Langfuse"):
        generate_candidates(frame, schema, config, dataset_ref="cleaned.pkl", run_id=run_id)
    assert transport.chat.call_count == 0
    tracing_factory.assert_not_called()
    audit = json.loads(
        (tmp_path / "runs" / str(run_id) / "analysis_proposer.json").read_text("utf-8")
    )
    assert audit["status"] == "failed"
    assert audit["settings"]["trace_backend"] == "local"
    assert "response" not in audit


def test_model_failure_never_calls_scan_and_is_not_retried(
    inputs: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame, schema, config = inputs
    _, observation, _, transport = install_fake_model(monkeypatch, [claim()])
    transport.chat.side_effect = TimeoutError("offline")
    run_id = uuid4()
    for _ in range(2):
        with pytest.raises(proposer.ProposerUnavailable):
            generate_candidates(frame, schema, config, dataset_ref="cleaned.pkl", run_id=run_id)
    assert transport.chat.call_count == 1
    assert any(call.kwargs.get("level") == "ERROR" for call in observation.update.call_args_list)


@pytest.mark.parametrize(
    "change", [{"done_reason": "length"}, {"model": "qwen2.5:7b"}, {"done": False}]
)
def test_incomplete_or_substituted_model_response_is_refused(
    inputs: tuple,
    monkeypatch: pytest.MonkeyPatch,
    change: dict,
) -> None:
    frame, schema, config = inputs
    _, _, _, transport = install_fake_model(monkeypatch, [claim()])
    transport.chat.return_value.update(change)
    with pytest.raises(proposer.ProposerUnavailable):
        generate_candidates(frame, schema, config, dataset_ref="cleaned.pkl", run_id=uuid4())


def test_invalid_column_roles_references_and_duplicates_do_not_reach_gateway(
    inputs: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame, schema, config = inputs
    install_fake_model(
        monkeypatch,
        [
            claim(),
            claim(),
            claim(variables=["missing", "bmi"]),
            claim(variables=["area", "bmi"]),
            claim(reference_group="invented"),
        ],
    )
    result = generate_candidates(frame, schema, config, dataset_ref="cleaned.pkl", run_id=uuid4())
    assert len(result) == 1


def test_wrong_model_direction_is_not_corrected_from_observed_data(inputs: tuple) -> None:
    frame, schema, config = inputs
    result = proposer.render_candidate(
        proposer.StructuredClaim.model_validate(claim(direction="negative")),
        frame,
        schema,
        config,
        dataset_ref="cleaned.pkl",
        allowed={"age", "bmi"},
    )
    assert result is not None
    assert result.asserted_direction is Direction.NEGATIVE
    assert result.analysis_evidence["raw_value"] > 0
    assert "negatively" in result.claim


def test_groups_trends_and_claim_screen_preserve_structured_meaning(inputs: tuple) -> None:
    frame, schema, config = inputs
    group = proposer.StructuredClaim.model_validate(
        claim(
            claim_type="group_difference",
            variables=["area", "income"],
            reference_group="urban",
        )
    )
    result = proposer.render_candidate(
        group, frame, schema, config, dataset_ref="cleaned.pkl", allowed=set(frame.columns)
    )
    assert result is not None
    assert result.reference_group == "urban"
    assert result.variables == ["area", "income"]
    assert "p_value" not in result.analysis_evidence
    assert (
        proposer.render_candidate(
            group,
            frame,
            schema,
            config,
            dataset_ref="cleaned.pkl",
            allowed=set(frame.columns),
            claim_screen=lambda *_: False,
        )
        is None
    )
    time = proposer.StructuredClaim.model_validate(
        claim(
            claim_type="trend",
            variables=["month", "visits"],
        )
    )
    assert schema.columns["month"].is_time_like
    assert (
        proposer.render_candidate(
            time, frame, schema, config, dataset_ref="cleaned.pkl", allowed=set(frame.columns)
        )
        is not None
    )
    assert schema.columns["area"].role is ColumnRole.CATEGORICAL


def test_explicit_engine_override_and_run_uuid_requirement(
    inputs: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRAMANA_ANALYSIS_ENGINE", "api")
    assert load_config().hypotheses.proposer.engine == "api"
    frame, schema, config = inputs
    from structlog.contextvars import clear_contextvars

    clear_contextvars()
    with pytest.raises(proposer.ProposerUnavailable, match="UUID"):
        generate_candidates(frame, schema, config, dataset_ref="cleaned.pkl")
