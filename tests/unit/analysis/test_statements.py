"""Statement checks: every figure is known from the planted table, not from the code under test."""

from __future__ import annotations

import json
from uuid import uuid4

import pandas as pd
import pytest

from pramana.analysis import infer_schema, load_config
from pramana.analysis.statements.check import check_statement, parse_period
from pramana.analysis.statements.models import (
    AssociationStatement,
    CausalStatement,
    ChangeStatement,
    ForecastStatement,
    RankStatement,
    ShareStatement,
)
from pramana.analysis.statements.parse import parse_statements
from pramana.common.llm_client import Completion

#: Quarter totals: Q3 2023 is 9.8% below Q2 2023 and 12.0% below Q3 2022.
TOTALS = {"2022Q3": 1025.0, "2023Q2": 1000.0, "2023Q3": 902.0}


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    rows = []
    for quarter in pd.period_range("2022Q1", "2023Q4", freq="Q"):
        total = TOTALS.get(str(quarter), 1000.0)
        for month in range(3):
            stamp = quarter.start_time + pd.DateOffset(months=month)
            for region, share in (("North", 0.6), ("South", 0.4)):
                rows.append({"month": stamp, "region": region, "revenue": total * share / 3})
    return pd.DataFrame(rows)


def change(pct: float | None, **kw):
    return ChangeStatement(
        kind="change",
        measure="revenue",
        granularity="quarter",
        to_period="2023Q3",
        stated_pct=pct,
        **kw,
    )


def run(statement, table, **kw):
    return check_statement(statement, table, time_column="month", additive=True, **kw)


def test_a_stated_fall_that_matches_the_previous_quarter(table) -> None:
    result = run(change(-9.8), table)
    assert result.status == "matches"
    assert result.readings[0].value == pytest.approx(-9.8, abs=0.01)


def test_a_figure_that_fits_only_the_other_comparison_is_ambiguous(table) -> None:
    result = run(change(-12.0), table)
    assert result.status == "ambiguous"
    assert "same period a year earlier" in result.headline and "-12.0%" in result.headline
    assert run(change(-12.0, baseline="year_ago"), table).status == "matches"


def test_a_wrong_figure_is_off_by_the_right_amount(table) -> None:
    result = run(change(-20.0), table)
    assert result.status == "off_by"
    assert result.values["off_by_points"] == pytest.approx(10.2, abs=0.05)


def test_missing_pieces_are_cannot_check_not_a_pass(table) -> None:
    assert run(change(None), table).status == "cannot_check"
    assert (
        check_statement(change(-9.8), table, time_column=None, additive=True).status
        == "cannot_check"
    )
    late = ChangeStatement(
        kind="change", measure="revenue", granularity="quarter", to_period="2031Q1", stated_pct=-5
    )
    assert run(late, table).status == "cannot_check"


def test_share_and_rank(table) -> None:
    def share(pct):
        return ShareStatement(
            kind="share", measure="revenue", group_column="region", group="north", stated_pct=pct
        )

    assert run(share(60), table).status == "matches"
    assert run(share(70), table).status == "off_by"

    def rank(group):
        return RankStatement(
            kind="rank", measure="revenue", group_column="region", group=group, position="highest"
        )

    assert run(rank("North"), table).status == "matches"
    wrong = run(rank("South"), table)
    assert wrong.status == "off_by" and "North" in wrong.headline


def test_causes_and_projections_are_not_testable_with_a_reason(table) -> None:
    cause = run(CausalStatement(kind="causal", cause="the discount", effect="sales"), table)
    assert cause.status == "not_testable" and "experiment" in cause.detail
    future = run(
        ForecastStatement(kind="forecast", measure="revenue", horizon="next quarter"), table
    )
    assert future.status == "not_testable" and "backtest" in future.detail


def test_an_association_links_to_the_gateway_result_when_there_is_one(table) -> None:
    claim = AssociationStatement(kind="association", x="a", y="b")
    assert run(claim, table).status == "not_tested"
    tested = [{"x": "b", "y": "a", "verdict": "PASS", "q": 0.0012}]
    result = run(claim, table, tested=tested)
    assert result.status == "tested" and "PASS" in result.headline


@pytest.mark.parametrize(
    ("label", "granularity", "expected"),
    [
        ("2023Q3", "quarter", "2023Q3"),
        ("Q3 2023", "quarter", "2023Q3"),
        ("2023-09", "month", "2023-09"),
        ("Sep 2023", "month", "2023-09"),
        ("2023", "year", "2023"),
        ("Q5 2023", "quarter", None),
    ],
)
def test_period_labels(label, granularity, expected) -> None:
    got = parse_period(label, granularity)
    assert (None if got is None else str(got)) == expected


def test_the_parser_keeps_only_statements_about_real_columns(table) -> None:
    schema = infer_schema(table, load_config().schema_inference)
    reply = {
        "statements": [
            {
                "kind": "change",
                "measure": "revenue",
                "granularity": "quarter",
                "to_period": "2023Q3",
                "stated_pct": -12,
            },
            {
                "kind": "change",
                "measure": "ghost",
                "granularity": "quarter",
                "to_period": "2023Q3",
                "stated_pct": -1,
            },
            {"kind": "mystery"},
        ]
    }
    chat = lambda messages: Completion(content=json.dumps(reply), input_tokens=1, output_tokens=1)
    statements, notes = parse_statements(
        "Revenue fell 12% in Q3", table, schema, time_column="month", trace_id=uuid4(), chat=chat
    )
    assert [s.kind for s in statements] == ["change"] and len(notes) == 2
    with pytest.raises(ValueError):
        parse_statements(
            "x",
            table,
            schema,
            time_column="month",
            trace_id=uuid4(),
            chat=lambda m: Completion(content="no", input_tokens=1, output_tokens=1),
        )
