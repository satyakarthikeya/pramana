"""The rule-based assistant drives the same chat loop and guards as the model."""

from __future__ import annotations

from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from pramana.analysis import infer_schema, load_config
from pramana.analysis.workspace import load_workspace_config
from pramana.chat.engine import run_chat_turn
from pramana.chat.rules import RuleChat
from pramana.chat.service import chat_engine
from tests.unit.chat.test_engine import Verifier


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(5)
    n = 240
    age = rng.integers(20, 80, n).astype(float)
    return pd.DataFrame(
        {
            "age": age,
            "region": rng.choice(["north", "south", "east"], n),
            "sex": rng.choice(["female", "male"], n),
            "systolic_bp": 100 + 0.6 * age + rng.normal(0, 8, n),
            "income": np.where(rng.random(n) < 0.1, np.nan, rng.normal(50, 10, n)),
        }
    )


def ask(frame: pd.DataFrame, question: str, verify: Verifier | None = None):
    config = load_config()
    return run_chat_turn(
        question,
        frame,
        infer_schema(frame, config.schema_inference),
        config.hypotheses,
        load_workspace_config(),
        dataset_ref="test.csv",
        message_id=uuid4(),
        chat=RuleChat(),
        verify=verify or Verifier(),
    )


def test_average_is_answered_from_the_tool_result(frame: pd.DataFrame) -> None:
    answer = ask(frame, "What is the average age?")
    assert answer.kind == "descriptive"
    assert f"{frame['age'].mean():.2f}" in answer.text
    assert answer.evidence and answer.evidence[0].tool == "describe"


def test_missing_values_are_listed(frame: pd.DataFrame) -> None:
    answer = ask(frame, "Which columns have missing values?")
    assert "income" in answer.text
    assert str(int(frame["income"].isna().sum())) in answer.text


def test_group_summary_is_exploratory(frame: pd.DataFrame) -> None:
    answer = ask(frame, "average systolic_bp by region")
    assert answer.kind == "exploratory"
    assert "north" in answer.text


def test_relationship_goes_to_the_gateway(frame: pd.DataFrame) -> None:
    verify = Verifier()
    answer = ask(frame, "Is age associated with systolic bp?", verify)
    assert [c.claim_type.value for c in verify.calls] == ["correlation"]
    assert set(verify.calls[0].variables) == {"age", "systolic_bp"}
    assert answer.tested is not None


def test_two_group_difference_sets_reference_and_direction(frame: pd.DataFrame) -> None:
    verify = Verifier()
    ask(frame, "Does systolic_bp differ by sex?", verify)
    (candidate,) = verify.calls
    assert candidate.claim_type.value == "group_difference"
    assert candidate.reference_group in {"female", "male"}


def test_unmatched_question_names_the_columns(frame: pd.DataFrame) -> None:
    answer = ask(frame, "tell me something interesting")
    assert "age" in answer.text and answer.tested is None


def test_engine_follows_the_analysis_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRAMANA_CHAT_ENGINE", raising=False)
    monkeypatch.setenv("PRAMANA_ANALYSIS_ENGINE", "deterministic")
    assert chat_engine() == "rules"
    monkeypatch.setenv("PRAMANA_ANALYSIS_ENGINE", "planner")
    assert chat_engine() == "model"
    monkeypatch.setenv("PRAMANA_CHAT_ENGINE", "rules")
    assert chat_engine() == "rules"
    monkeypatch.setenv("PRAMANA_CHAT_ENGINE", "bogus")
    with pytest.raises(ValueError):
        chat_engine()
