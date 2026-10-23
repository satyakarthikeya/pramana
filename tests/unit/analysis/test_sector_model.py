"""DeepSeek picks the sector; code accepts only a known pack (PLAN §14, amended 2026-10-23)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import uuid4

import pandas as pd
import pytest

from pramana.analysis import infer_schema, load_config
from pramana.analysis.sector_model import SectorModelUnavailable, detect_sector_with_model
from pramana.analysis.sectors import load_packs
from pramana.common.llm_client import ChatMessage, Completion
from tests.unit.analysis import computed_fixtures as fx


def _reply(content: str):
    sent: list[Sequence[ChatMessage]] = []

    def chat(messages: Sequence[ChatMessage]) -> Completion:
        sent.append(messages)
        return Completion(content=content, input_tokens=10, output_tokens=5)

    return chat, sent


def _detect(frame: pd.DataFrame, chat):
    schema = infer_schema(frame, load_config().schema_inference)
    return detect_sector_with_model(frame, schema, load_packs(), trace_id=uuid4(), chat=chat)


def test_the_model_decides_the_sector_and_code_fills_the_roles() -> None:
    chat, sent = _reply(json.dumps({"sector": "finance"}))
    match = _detect(fx.finance_year(), chat)
    assert match.sector == "finance"
    assert match.roles["revenue"] == "amount"
    assert any("model" in reason for reason in match.reasons)
    assert len(sent) == 1


def test_the_model_can_overrule_the_vocabulary() -> None:
    chat, _ = _reply(json.dumps({"sector": "general"}))
    assert _detect(fx.finance_year(), chat).sector == "general"


def test_an_unknown_sector_from_the_model_falls_back_to_rules_and_says_so() -> None:
    chat, _ = _reply(json.dumps({"sector": "astrology"}))
    match = _detect(fx.finance_year(), chat)
    assert match.sector == "finance"
    assert any("rules" in reason for reason in match.reasons)


def test_a_malformed_reply_falls_back_to_rules() -> None:
    chat, _ = _reply("sure, it is finance!")
    match = _detect(fx.health_sample(), chat)
    assert match.sector == "health"
    assert any("rules" in reason for reason in match.reasons)


def test_an_unavailable_model_falls_back_to_rules_and_says_so() -> None:
    def chat(_messages):
        raise SectorModelUnavailable("DEEPSEEK_API_KEY is not set")

    match = _detect(fx.finance_year(), chat)
    assert match.sector == "finance"
    assert any("unavailable" in reason for reason in match.reasons)


def test_the_model_sees_column_names_and_roles_but_never_values() -> None:
    frame = fx.finance_year()
    frame.loc[0, "revenue"] = 987654.321
    chat, sent = _reply(json.dumps({"sector": "finance"}))
    _detect(frame, chat)
    prompt = "\n".join(m.content for m in sent[0])
    assert "revenue" in prompt and "region" in prompt
    assert "987654" not in prompt
    assert "North" not in prompt  # category values are data, not names


def test_rules_engine_never_calls_a_model(monkeypatch) -> None:
    from pramana.api import datasets

    monkeypatch.setenv("PRAMANA_SECTOR_ENGINE", "rules")

    def boom(*_a, **_k):
        raise AssertionError("model called")

    monkeypatch.setattr(datasets, "detect_sector_with_model", boom)
    frame = fx.finance_year()
    schema = infer_schema(frame, load_config().schema_inference)
    result = datasets.exact_tier(frame, schema, trace_id=uuid4())
    assert result is not None and result.sector.sector == "finance"


def test_api_engine_uses_the_model(monkeypatch) -> None:
    from pramana.analysis.sectors import SectorMatch
    from pramana.api import datasets

    monkeypatch.setenv("PRAMANA_SECTOR_ENGINE", "api")
    calls = []

    def fake(frame, schema, packs, *, trace_id, chat=None):
        calls.append(trace_id)
        return SectorMatch(sector="health", label="Health", score=0, reasons=["chosen by model"])

    monkeypatch.setattr(datasets, "detect_sector_with_model", fake)
    frame = fx.finance_year()
    schema = infer_schema(frame, load_config().schema_inference)
    trace = uuid4()
    result = datasets.exact_tier(frame, schema, trace_id=trace)
    assert calls == [trace]
    assert result is not None and result.sector.sector == "health"


@pytest.mark.parametrize("engine", ["api", "rules"])
def test_engine_setting_is_validated(monkeypatch, engine) -> None:
    from pramana.analysis.computed import load_computed_config

    monkeypatch.setenv("PRAMANA_SECTOR_ENGINE", engine)
    assert load_computed_config().sector_engine == engine
