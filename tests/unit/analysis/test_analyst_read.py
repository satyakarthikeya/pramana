"""The analyst agent: extra analyses it asks for and the paragraphs it writes.

The model is a scripted reply; every expectation comes from the planted table.
"""

from __future__ import annotations

import json
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from pramana.analysis.analyst.facts import associations, build_facts, leaderboard
from pramana.analysis.analyst.models import Fact
from pramana.analysis.analyst.read import build_read, choose_requests
from pramana.analysis.measured.drivers import run_driver
from pramana.analysis.measured.models import MeasuredAnalysis
from pramana.common.llm_client import Completion
from tests.unit.analysis import measured_fixtures as fx

CONFIG = fx.fast_config()


def planted(n: int = 240, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    return pd.DataFrame(
        {
            "income": x,
            "spend": 2.0 * x + 2.0 * rng.normal(size=n),
            "savings": -x + 1.5 * rng.normal(size=n),
            "noise": rng.normal(size=n),
        }
    )


def reply(payload: object):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return lambda messages: Completion(content=text, input_tokens=10, output_tokens=10)


@pytest.fixture(scope="module")
def table():
    frame = planted()
    schema, shape = fx.prepare(frame)
    item = run_driver(
        frame, schema, shape, task="regression", target="spend", config=CONFIG, roles={}
    )
    return frame, schema, shape, item


def test_driver_rows_say_which_way_each_column_moves(table) -> None:
    _, _, _, item = table
    assert item.status == "ok", item.sentence
    first = item.table[0]
    assert first["feature"] == "income" or first["feature"] == "savings"
    rho = float(first["rank_correlation"])  # type: ignore[arg-type]
    assert first["direction"] == ("higher" if rho > 0 else "lower")
    income = next(r for r in item.table if r["feature"] == "income")
    assert income["direction"] == "higher"


def test_associations_rank_the_planted_pair_first(table) -> None:
    frame, schema, _, _ = table
    fact = associations(frame, schema, {}, None)
    assert fact is not None
    top = fact.table[0]
    assert {top["column_a"], top["column_b"]} == {"income", "spend"}
    assert float(top["rank_correlation"]) > 0.5  # type: ignore[arg-type]
    assert top["rows"] == len(frame)


def test_leaderboard_lists_every_model_with_the_baseline(table) -> None:
    _, _, _, item = table
    board = leaderboard(item)
    assert board is not None and board.id == "leaderboard:spend"
    models = {r["model"] for r in board.table}
    assert {"ridge", "forest"} <= models
    scores = [float(r["held_out_score"]) for r in board.table]  # type: ignore[arg-type]
    assert scores == sorted(scores, reverse=True)
    assert board.values["baseline_score"] is not None


def facts_for(table) -> tuple[list[Fact], list[str]]:
    frame, schema, shape, item = table
    measured = MeasuredAnalysis(seed=1, n_rows=len(frame), items=[item])
    return build_facts(None, measured, frame, schema), list(frame.columns)


def test_a_paragraph_with_only_cited_numbers_is_kept(table) -> None:
    facts, names = facts_for(table)
    top = facts[0].table[0]
    rho = f"{float(top['rank_correlation']):.2f}"  # type: ignore[arg-type]
    good = {
        "paragraphs": [
            {
                "fact_ids": ["associations"],
                "text": f"{top['column_a']} and {top['column_b']} move together, with a rank "
                f"correlation of {rho} over {top['rows']} rows.",
            }
        ]
    }
    read = build_read(facts, names, [], trace_id=uuid4(), chat=reply(good))
    assert read.source == "model" and len(read.paragraphs) == 1
    assert read.paragraphs_dropped == 0


def test_paragraphs_with_invented_numbers_or_verdict_words_are_dropped(table) -> None:
    facts, names = facts_for(table)
    top = facts[0].table[0]
    rho = f"{float(top['rank_correlation']):.2f}"  # type: ignore[arg-type]
    mixed = {
        "paragraphs": [
            {"fact_ids": ["associations"], "text": "income and spend move together, rho 0.31."},
            {
                "fact_ids": ["associations"],
                "text": f"Income drives spend, with a rank correlation of {rho}.",
            },
            {"fact_ids": ["nope"], "text": f"Spend goes with income at {rho}."},
            {
                "fact_ids": ["associations"],
                "text": f"Spend goes with income at {rho} over {top['rows']} rows.",
            },
        ]
    }
    read = build_read(facts, names, [], trace_id=uuid4(), chat=reply(mixed))
    assert read.source == "model"
    assert [p.text for p in read.paragraphs] == [
        f"Spend goes with income at {rho} over {top['rows']} rows."
    ]
    assert read.paragraphs_dropped == 3


def test_when_every_paragraph_fails_the_code_sentences_are_shown(table) -> None:
    facts, names = facts_for(table)
    bad = {"paragraphs": [{"fact_ids": ["associations"], "text": "Spend is 37 percent income."}]}
    read = build_read(facts, names, [], trace_id=uuid4(), chat=reply(bad))
    assert read.source == "template"
    assert read.fallback_reason and "no paragraph passed" in read.fallback_reason
    assert read.paragraphs, "the code's own sentences are shown instead"


def test_a_broken_or_missing_model_falls_back_without_raising(table) -> None:
    facts, names = facts_for(table)
    garbled = build_read(facts, names, [], trace_id=uuid4(), chat=reply("not json"))
    assert garbled.source == "template" and "format" in (garbled.fallback_reason or "")

    def boom(messages):
        raise RuntimeError("down")

    assert build_read(facts, names, [], trace_id=uuid4(), chat=boom).source == "template"
    assert build_read(facts, names, [], trace_id=uuid4(), engine="template").source == "template"


def test_the_agent_may_ask_only_for_analyses_that_pass_code_checks(table) -> None:
    frame, schema, shape, _ = table
    asks = {
        "requests": [
            {"task": "driver_regression", "target": "savings", "features": []},
            {"task": "driver_regression", "target": "ghost", "features": []},
            {"task": "forecast", "target": "spend", "features": []},
            {"task": "driver_regression", "target": "spend", "features": []},
            {"task": "segments", "target": None, "features": []},
        ]
    }
    # the schema allows at most three; a longer list is a malformed reply and asks for nothing
    accepted, record = choose_requests(
        frame, schema, shape, {}, None, CONFIG, trace_id=uuid4(), chat=reply(asks)
    )
    assert (accepted, record) == ([], [])

    asks["requests"] = [asks["requests"][0], asks["requests"][1], asks["requests"][2]]
    accepted, record = choose_requests(
        frame, schema, shape, {}, None, CONFIG, trace_id=uuid4(), chat=reply(asks)
    )
    assert [(r.task, r.target) for r in accepted] == [("driver_regression", "savings")]
    assert [r.accepted for r in record] == [True, False, False]
    assert "not a column" in record[1].note and record[2].note == "not on the menu"
