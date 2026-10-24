"""Report slice (PLAN §13, 2026-10-24): chart data on Exact figures, and the summary."""

from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import uuid4

import pandas as pd
import pytest

from pramana.analysis import infer_schema, load_config
from pramana.analysis.computed import (
    COMPUTED_VERSION,
    ComputedAnalysis,
    ExactItem,
    compute_analysis,
)
from pramana.analysis.computed.summary import summarise
from pramana.common.llm_client import ChatMessage, Completion
from tests.unit.analysis import computed_fixtures as fx


def _run(frame: pd.DataFrame) -> ComputedAnalysis:
    return compute_analysis(frame, infer_schema(frame, load_config().schema_inference))


def _item(result: ComputedAnalysis, kind: str, column: str | None = None) -> ExactItem:
    return next(
        i for i in result.items if i.kind == kind and (column is None or column in i.columns)
    )


@pytest.fixture(scope="module")
def finance() -> ComputedAnalysis:
    return _run(fx.finance_year())


def test_the_analysis_carries_its_version(finance: ComputedAnalysis) -> None:
    assert finance.version == COMPUTED_VERSION >= 2


def test_period_change_line_has_the_same_totals_as_the_figure(finance: ComputedAnalysis) -> None:
    item = _item(finance, "period_change", "revenue")
    assert item.chart is not None and item.chart.kind == "line"
    points = dict(item.chart.points)
    assert len(points) == 12
    assert points[item.values["current_label"]] == pytest.approx(item.values["current"])
    assert points[item.values["previous_label"]] == pytest.approx(item.values["previous"])


def test_waterfall_steps_sum_to_the_change(finance: ComputedAnalysis) -> None:
    item = _item(finance, "variance_decomposition", "revenue")
    chart = item.chart
    assert chart is not None and chart.kind == "waterfall"
    steps = sum(step.value for step in chart.steps)
    assert steps == pytest.approx(item.values["total_change"])
    assert chart.start + steps == pytest.approx(chart.end)


def test_a_segment_that_moves_more_than_the_total_is_worded_plainly() -> None:
    # 12 months x 2 regions; from November to December A rises by 10.1 (10 plus the 0.1
    # monthly drift) and B falls by 6.1, so the total rises by 4.
    rows = []
    for m in range(12):
        a = 100.0 + m / 10 + (10.0 if m == 11 else 0.0)
        b = 200.0 - m / 10 - (6.0 if m == 11 else 0.0)
        for region, value in (("A", a), ("B", b)):
            rows.append({"month": f"2025-{m + 1:02d}-01", "region": region, "revenue": value})
    frame = pd.DataFrame(rows)
    item = _item(
        _run(frame.assign(cost=frame["revenue"] * 0.5)), "variance_decomposition", "revenue"
    )
    assert "%" not in item.sentence
    assert "A rose by 10.10 while total revenue rose by 4;" in item.sentence
    assert "together fell by 6.10" in item.sentence


def test_pareto_cumulative_share_ends_at_one(finance: ComputedAnalysis) -> None:
    chart = _item(finance, "concentration", "revenue").chart
    assert chart is not None and chart.kind == "pareto"
    shares = [bar.cumulative_share for bar in chart.bars]
    assert shares == sorted(shares) and shares[-1] == pytest.approx(1.0)


def test_outlier_line_marks_the_spike(finance: ComputedAnalysis) -> None:
    chart = _item(finance, "outliers", "cost").chart
    assert chart is not None and chart.kind == "line"
    assert any(mark.startswith("2025-03") for mark in chart.marks)


def test_seasonality_heat_strip_has_twelve_months() -> None:
    chart = _item(_run(fx.finance_two_years()), "seasonality", "revenue").chart
    assert chart is not None and chart.kind == "heat_strip"
    assert [c.label for c in chart.cells][-1] == "December" and len(chart.cells) == 12


def test_prevalence_bars_show_the_breakdown() -> None:
    chart = _item(_run(fx.health_sample()), "prevalence", "BMXBMI").chart
    assert chart is not None and chart.kind == "bar"
    assert {"Male", "Female"} <= {bar.label for bar in chart.bars}


def test_long_series_are_capped() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=900, freq="D").strftime("%Y-%m-%d"),
            "sales": [100.0 + (i % 17) for i in range(900)],
        }
    )
    for item in _run(frame).items:
        if item.chart is not None and item.chart.kind == "line":
            assert len(item.chart.points) <= 120


# --- summary -------------------------------------------------------------------------


def _chat(content: str):
    sent: list[Sequence[ChatMessage]] = []

    def chat(messages: Sequence[ChatMessage]) -> Completion:
        sent.append(messages)
        return Completion(content=content)

    return chat, sent


def _summary(result: ComputedAnalysis, chat=None, engine: str = "api"):
    return summarise(result, engine=engine, trace_id=uuid4(), chat=chat)


def test_template_summary_uses_code_sentences(finance: ComputedAnalysis) -> None:
    summary = _summary(finance, engine="template")
    assert summary.source == "template" and summary.fallback_reason is None
    ids = {i.id: i for i in finance.items}
    assert 1 <= len(summary.lines) <= 5
    for line in summary.lines:
        assert line.text == ids[line.item_id].sentence
    # the story leads with what happened, then why it moved
    assert summary.lines[0].item_id.startswith("period_change")
    assert any(ln.item_id.startswith("variance_decomposition") for ln in summary.lines)


def test_model_summary_is_kept_when_every_number_checks_out(finance: ComputedAnalysis) -> None:
    chat, sent = _chat(
        json.dumps(
            {
                "lines": [
                    {
                        "item_id": "variance_decomposition:revenue",
                        "text": "North accounts for 76.9% of the revenue rise "
                        "from 2025-11 to 2025-12.",
                    },
                ]
            }
        )
    )
    summary = _summary(finance, chat)
    assert summary.source == "model" and summary.fallback_reason is None
    assert summary.lines[0].text.startswith("North accounts for 76.9%")
    assert len(sent) == 1


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ({"lines": [{"item_id": "made_up:1", "text": "Revenue rose."}]}, "unknown"),
        (
            {
                "lines": [
                    {
                        "item_id": "variance_decomposition:revenue",
                        "text": "North accounts for 81% of the rise.",
                    }
                ]
            },
            "number",
        ),
        (
            {
                "lines": [
                    {
                        "item_id": "variance_decomposition:revenue",
                        "text": "North causes the rise in revenue.",
                    }
                ]
            },
            "wording",
        ),
        ("not json", "format"),
    ],
)
def test_a_bad_model_summary_falls_back_with_its_reason(
    finance: ComputedAnalysis, reply, reason: str
) -> None:
    chat, _ = _chat(reply if isinstance(reply, str) else json.dumps(reply))
    summary = _summary(finance, chat)
    assert summary.source == "template"
    assert summary.fallback_reason and reason in summary.fallback_reason
    assert summary.lines == _summary(finance, engine="template").lines


def test_the_summary_model_sees_figures_not_rows(finance: ComputedAnalysis) -> None:
    chat, sent = _chat(json.dumps({"lines": []}))
    _summary(finance, chat)
    prompt = "\n".join(m.content for m in sent[0])
    assert "variance_decomposition:revenue" in prompt
    assert "2025-01-01" not in prompt  # raw row values never leave; period labels do
