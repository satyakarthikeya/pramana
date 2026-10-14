"""Gemma can label a column only inside a traced run and within value constraints."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pandas as pd
import pytest
from pydantic import ValidationError

from pramana.analysis.config import GemmaSettings, load_config
from pramana.analysis.gemma import GemmaSemanticRefiner, SemanticDecision
from pramana.analysis.schema_inference import (
    ColumnRole,
    infer_schema,
    infer_schema_with_gemma,
)


def test_candidate_generation_uses_refined_roles_only_as_proposals(
    transport: dict[str, Any],
) -> None:
    from pramana.analysis import analyse

    _, candidates = analyse(numeric_strings(), dataset_ref="cleaned-artifact", run_id=uuid4())
    assert candidates
    assert len(transport["calls"]) == 1
    assert all(
        not {"p_value", "q_value", "verdict", "verified"} & set(item.analysis_evidence)
        for item in candidates
    )


def test_handler_analysis_reuses_preparation_schema_without_a_second_model_call(
    transport: dict[str, Any],
) -> None:
    from pramana.analysis.handlers import analyze

    data = numeric_strings()
    run_id = uuid4()
    schema = infer_schema_with_gemma(data, load_config().schema_inference, run_id=run_id)
    result = analyze(
        {
            "run_id": run_id,
            "dataset": data,
            "dataset_ref": "cleaned-artifact",
            "schema_profile": schema.model_dump(mode="json"),
        }
    )
    assert result["candidate_insights"]
    assert len(transport["calls"]) == 1


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {
        "calls": [],
        "traces": [],
        "active": False,
        "content": '{"role":"numeric","confidence":0.9,"reason":"numbers"}',
    }
    monkeypatch.delenv("GEMMA_MODEL", raising=False)
    monkeypatch.delenv("GEMMA_BASE_URL", raising=False)

    class Observation:
        def update(self, **kwargs: Any) -> None:
            seen["output"] = kwargs

    class Tracing:
        @contextmanager
        def start_as_current_observation(self, **kwargs: Any) -> Iterator[Observation]:
            seen["traces"].append(kwargs)
            seen["active"] = True
            try:
                yield Observation()
            finally:
                seen["active"] = False

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            seen["client"] = kwargs

        def chat(self, **kwargs: Any) -> SimpleNamespace | dict[str, Any]:
            assert seen["active"], "model request must happen inside a Langfuse observation"
            seen["calls"].append(kwargs)
            if error := seen.get("error"):
                raise error
            if seen.get("mapping_response"):
                return {"message": {"content": seen["content"]}}
            return SimpleNamespace(message=SimpleNamespace(content=seen["content"]))

    monkeypatch.setattr("pramana.analysis.gemma.get_langfuse_client", lambda _settings: Tracing())
    monkeypatch.setattr("ollama.Client", Client)
    return seen


def numeric_strings() -> pd.DataFrame:
    return pd.DataFrame({"encoded": [str(i) for i in range(40)], "measurement": range(40)})


def test_public_schema_path_uses_traced_gemma_without_mutating_data(
    transport: dict[str, Any],
) -> None:
    from pramana.analysis import infer_schema as public_infer_schema

    data = numeric_strings()
    before = data.copy(deep=True)
    config = load_config().schema_inference
    run_id = uuid4()
    assert infer_schema(data, config).role_of("encoded") is ColumnRole.UNKNOWN
    result = public_infer_schema(data, config, run_id=run_id)
    assert result.role_of("encoded") is ColumnRole.NUMERIC
    assert result.columns["encoded"].confidence == config.min_confidence
    pd.testing.assert_frame_equal(data, before)
    assert len(transport["calls"]) == 1
    trace = transport["traces"][0]
    assert trace["trace_context"] == {"trace_id": run_id.hex}
    assert trace["metadata"]["run_id"] == str(run_id)
    assert "sample_values" not in trace["input"] and "levels" not in trace["input"]
    request = transport["calls"][0]
    assert request["model"] == config.gemma.model
    assert request["format"] == SemanticDecision.model_json_schema()
    assert request["options"]["seed"] == config.gemma.seed
    assert transport["client"]["timeout"] == config.gemma.timeout_seconds
    assert transport["client"]["trust_env"] is False


def test_graph_bound_run_uuid_is_used(transport: dict[str, Any]) -> None:
    from pramana.common.logging import bind_run_context, clear_log_context

    run_id = uuid4()
    bind_run_context(str(run_id))
    try:
        infer_schema_with_gemma(numeric_strings(), load_config().schema_inference)
    finally:
        clear_log_context()
    assert transport["traces"][0]["metadata"]["run_id"] == str(run_id)


@pytest.mark.parametrize("mode", ["no_run", "disabled", "heuristics_only", "no_trace"])
def test_unavailable_or_disabled_refinement_makes_no_model_call(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    config = load_config().schema_inference
    run_id = None if mode == "no_run" else uuid4()
    if mode == "disabled":
        config = config.model_copy(
            update={"gemma": config.gemma.model_copy(update={"enabled": False})}
        )
    if mode == "heuristics_only":
        config = config.model_copy(update={"use_llm_for_ambiguous_only": False})
    if mode == "no_trace":
        monkeypatch.setattr("pramana.analysis.gemma.get_langfuse_client", lambda _settings: None)
    result = infer_schema_with_gemma(numeric_strings(), config, run_id=run_id)
    assert result.role_of("encoded") is ColumnRole.UNKNOWN
    assert transport["calls"] == []


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not JSON",
        '{"role":"verified","confidence":1,"reason":"ok"}',
        '{"role":"numeric","confidence":1,"reason":"ok","verdict":"PASS"}',
        '{"role":"numeric","confidence":0.2,"reason":"unsure"}',
        '{"role":"unknown","confidence":1,"reason":"unsure"}',
        '{"role":"id_like","confidence":1,"reason":"identifier"}',
        '{"role":"datetime","confidence":1,"reason":"time"}',
    ],
)
def test_bad_or_unsupported_response_leaves_column_unknown(
    transport: dict[str, Any], content: str
) -> None:
    transport["content"] = content
    result = infer_schema_with_gemma(
        numeric_strings(), load_config().schema_inference, run_id=uuid4()
    )
    assert result.role_of("encoded") is ColumnRole.UNKNOWN
    assert result.columns["encoded"].usable_for_hypotheses is False


def test_network_timeout_leaves_heuristic_roles_intact(transport: dict[str, Any]) -> None:
    transport["error"] = TimeoutError("local model timed out")
    data = numeric_strings()
    result = infer_schema_with_gemma(data, load_config().schema_inference, run_id=uuid4())
    assert result.role_of("encoded") is ColumnRole.UNKNOWN
    assert result.role_of("measurement") is ColumnRole.NUMERIC


def test_constant_columns_are_never_sent_to_gemma(transport: dict[str, Any]) -> None:
    infer_schema_with_gemma(
        pd.DataFrame({"constant": [1] * 40}), load_config().schema_inference, run_id=uuid4()
    )
    assert transport["calls"] == []


def test_per_pass_call_budget_is_enforced(transport: dict[str, Any]) -> None:
    config = load_config().schema_inference
    config = config.model_copy(
        update={"gemma": config.gemma.model_copy(update={"max_columns_per_pass": 1})}
    )
    data = numeric_strings().assign(second=[str(i) for i in range(40)])
    result = infer_schema_with_gemma(data, config, run_id=uuid4())
    assert result.role_of("encoded") is ColumnRole.NUMERIC
    assert result.role_of("second") is ColumnRole.UNKNOWN
    assert len(transport["calls"]) == 1


def test_model_cannot_turn_free_text_into_numeric(transport: dict[str, Any]) -> None:
    data = pd.DataFrame({"notes": [f"note number {i}" for i in range(40)]})
    result = infer_schema_with_gemma(data, load_config().schema_inference, run_id=uuid4())
    assert result.role_of("notes") is ColumnRole.UNKNOWN


def test_refined_datetime_gets_a_time_axis_flag(transport: dict[str, Any]) -> None:
    transport["content"] = '{"role":"datetime","confidence":1,"reason":"dates"}'
    config = load_config().schema_inference.model_copy(update={"min_confidence": 0.95})
    data = pd.DataFrame({"observed": pd.date_range("2026-01-01", periods=40).astype(str)})
    result = infer_schema_with_gemma(data, config, run_id=uuid4())
    assert result.columns["observed"].is_time_like
    assert result.role_of("observed") is ColumnRole.DATETIME


@pytest.mark.parametrize("bad", ["qwen2.5:7b", "deepseek-v4", "gemma2:cloud"])
def test_nonlocal_or_non_gemma_model_is_refused(bad: str) -> None:
    settings = load_config().schema_inference.gemma.model_dump()
    settings["model"] = bad
    with pytest.raises(ValidationError, match="local Gemma"):
        GemmaSettings.model_validate(settings)


@pytest.mark.parametrize(
    "bad",
    [
        "https://api.example.com",
        "http://localhost@api.example.com",
        "http://localhost:11434/api/chat",
    ],
)
def test_remote_endpoint_is_refused(bad: str) -> None:
    settings = load_config().schema_inference.gemma.model_dump()
    settings["base_url"] = bad
    with pytest.raises(ValidationError, match="local Ollama"):
        GemmaSettings.model_validate(settings)


def test_environment_cannot_silently_substitute_qwen(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEMMA_MODEL", "qwen2.5:7b")
    with pytest.raises(ValidationError, match="local Gemma"):
        GemmaSemanticRefiner(numeric_strings(), load_config().schema_inference, uuid4())
    assert transport["calls"] == []


def test_tracing_start_failure_prevents_the_model_request(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenTracing:
        def start_as_current_observation(self, **_kwargs: Any) -> None:
            raise RuntimeError("cannot start trace")

    monkeypatch.setattr(
        "pramana.analysis.gemma.get_langfuse_client", lambda _settings: BrokenTracing()
    )
    result = infer_schema_with_gemma(
        numeric_strings(), load_config().schema_inference, run_id=uuid4()
    )
    assert result.role_of("encoded") is ColumnRole.UNKNOWN
    assert transport["calls"] == []


def test_ollama_mapping_response_is_supported(transport: dict[str, Any]) -> None:
    transport["mapping_response"] = True
    result = infer_schema_with_gemma(
        numeric_strings(), load_config().schema_inference, run_id=uuid4()
    )
    assert result.role_of("encoded") is ColumnRole.NUMERIC


def test_shared_legacy_langfuse_api_is_supported(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Generation:
        def update(self, **kwargs: Any) -> None:
            transport["output"] = kwargs

        def end(self) -> None:
            transport["active"] = False

    class Trace:
        def generation(self, **kwargs: Any) -> Generation:
            transport["active"] = True
            transport["legacy_generation"] = kwargs
            return Generation()

    class Legacy:
        def trace(self, **kwargs: Any) -> Trace:
            transport["legacy_trace"] = kwargs
            return Trace()

    monkeypatch.setattr("pramana.analysis.gemma.get_langfuse_client", lambda _settings: Legacy())
    run_id = uuid4()
    result = infer_schema_with_gemma(
        numeric_strings(), load_config().schema_inference, run_id=run_id
    )
    assert result.role_of("encoded") is ColumnRole.NUMERIC
    assert transport["legacy_trace"] == {"id": str(run_id)}
    assert transport["legacy_generation"]["metadata"]["run_id"] == str(run_id)
    assert transport["active"] is False
