"""Regression tests for the bugs found in the review of the sector-analysis branch."""

from __future__ import annotations

import json
from uuid import uuid4

import numpy as np
import pandas as pd

from pramana.analysis import infer_schema, load_config
from pramana.analysis.computed import ComputedAnalysis, ExactItem, compute_analysis
from pramana.analysis.computed.summary import summarise
from pramana.analysis.schema_inference import infer_column
from pramana.common.llm_client import Completion
from tests.unit.analysis import computed_fixtures as fx


def _run(frame: pd.DataFrame) -> ComputedAnalysis:
    return compute_analysis(frame, infer_schema(frame, load_config().schema_inference))


def _items(result: ComputedAnalysis, kind: str, column: str | None = None) -> list[ExactItem]:
    return [i for i in result.items if i.kind == kind and (column is None or column in i.columns)]


def test_infinite_values_are_ignored_and_the_result_reloads() -> None:
    frame = fx.finance_year()
    frame.loc[0, "revenue"] = np.inf
    result = _run(frame)
    for item in result.items:
        assert "nan" not in item.sentence.lower() and "inf" not in item.sentence.lower(), item.id
    ComputedAnalysis.model_validate_json(result.model_dump_json())  # round-trips


def test_rows_with_a_missing_segment_still_count_towards_the_change() -> None:
    frame = fx.finance_year()
    frame.loc[frame.index[-3:], "region"] = None
    result = _run(frame)
    change = _items(result, "period_change", "revenue")[0].values["change"]
    split = _items(result, "variance_decomposition", "revenue")[0]
    assert split.values["total_change"] == change
    assert "(missing)" in {row["segment"] for row in split.table}


def test_a_negative_average_has_no_seasonal_peak() -> None:
    frame = fx.finance_two_years()
    frame["revenue"] = -frame["revenue"]
    assert not [i for i in _items(_run(frame), "seasonality") if i.status == "ok"]


def test_year_on_year_windows_need_every_calendar_month() -> None:
    # 25 months with 2025-07 missing: still 24 distinct months, but not 24 calendar months
    frame = fx.finance_two_years()
    extra = frame[frame["month"] == "2025-12-01"].assign(month="2026-01-01")
    frame = pd.concat([frame, extra], ignore_index=True)
    frame = frame[frame["month"] != "2025-07-01"]
    item = _items(_run(frame), "period_change", "revenue")[0]
    assert "12 months" not in item.sentence  # falls back to latest vs previous month
    assert item.values["current_label"] == "2026-01"


def test_concentration_refuses_negative_segment_totals() -> None:
    rows = []
    for m in range(1, 13):
        for region, value in (("A", 100.0 + m), ("B", 50.0 + m), ("C", -120.0 - m)):
            rows.append(
                {
                    "month": f"2025-{m:02d}-01",
                    "region": region,
                    "profit": value,
                    "revenue": abs(value) + 1,
                }
            )
    result = _run(pd.DataFrame(rows))
    for item in _items(result, "concentration", "profit"):
        assert item.status == "not_run"
    for item in _items(result, "concentration"):
        if item.status == "ok":
            assert 0 <= item.values["top_share"] <= 1


def test_refused_and_dont_know_answers_are_left_out_of_a_share() -> None:
    frame = fx.health_sample(with_weights=False)
    frame["SMQ020"] = [1] * 10 + [2] * 20 + [7] * 5 + [9] * 5
    item = _items(_run(frame), "prevalence", "SMQ020")[0]
    assert item.values["share"] == 10 / 30
    assert item.values["n"] == 30


def test_a_year_column_with_a_gap_reads_as_whole_years() -> None:
    years = [2015 + i for i in range(30)]
    frame = pd.DataFrame({"year": years, "sales": [100.0 + 3 * i for i in range(30)]})
    frame.loc[5, "year"] = None
    item = _items(_run(frame), "period_change", "sales")[0]
    assert ".0" not in item.sentence


def test_a_negative_base_gives_no_percentage() -> None:
    rows = []
    for m in range(1, 13):
        for region in ("A", "B"):
            rows.append(
                {
                    "month": f"2025-{m:02d}-01",
                    "region": region,
                    "revenue": 100.0 + m,
                    "profit": -50.0 + m,
                }
            )
    item = _items(_run(pd.DataFrame(rows)), "period_change", "profit")[0]
    assert "change_pct" not in item.values
    assert "%" not in item.sentence


def test_a_summary_line_must_quote_its_figure_and_carry_no_links() -> None:
    result = _run(fx.finance_year())

    def reply(text: str):
        payload = {"lines": [{"item_id": "variance_decomposition:revenue", "text": text}]}
        return lambda _m: Completion(content=json.dumps(payload))

    for text in ("North is the region to watch.", "North: see https://evil.example 76.9%"):
        summary = summarise(result, engine="api", trace_id=uuid4(), chat=reply(text))
        assert summary.source == "template", text


def test_dates_with_mixed_time_zones_do_not_crash_the_upload() -> None:
    series = pd.Series(
        ["2025-01-01T10:00:00+05:30", "2025-01-02T10:00:00+00:00", "2025-01-03T10:00:00-04:00"] * 20
    )
    profile = infer_column(series, "created_at", load_config().schema_inference)
    assert profile.role.value == "datetime"
