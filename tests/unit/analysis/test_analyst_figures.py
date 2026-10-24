"""The analyst figures: price/volume/mix, segment growth, customers, rolling seasonality, story.

Every expectation below is computed by hand from the planted table, not from the code.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.analysis import infer_schema, load_config
from pramana.analysis.computed import ComputedAnalysis, ExactItem, compute_analysis, load_computed_config


def _run(frame: pd.DataFrame) -> ComputedAnalysis:
    return compute_analysis(frame, infer_schema(frame, load_config().schema_inference))


def _item(result: ComputedAnalysis, kind: str) -> ExactItem:
    found = [i for i in result.items if i.kind == kind]
    assert found, [i.id for i in result.items]
    return found[0]


def _monthly(rows_by_year: dict[int, dict[str, tuple[float, float]]]) -> pd.DataFrame:
    """Two years of months; per region and year a (units per month, price) pair."""
    rows = []
    for year, regions in rows_by_year.items():
        for month in pd.period_range(f"{year}-01", f"{year}-12", freq="M"):
            for region, (units, price) in regions.items():
                rows.append(
                    {
                        "month": month.to_timestamp().date().isoformat(),
                        "region": region,
                        "units": units,
                        "revenue": units * price,
                        "cost": units * price * 0.5,
                    }
                )
    return pd.DataFrame(rows)


# --- price / volume / mix ------------------------------------------------------------


def test_price_volume_mix_matches_the_hand_calculation() -> None:
    # Year 1: A 10 units/month at 10, B 10 at 20. Year 2: A 15 at 11, B 5 at 20.
    # Totals: Q0 = Q1 = 240, R0 = 3600, R1 = 3180.
    frame = _monthly({2023: {"A": (10, 10.0), "B": (10, 20.0)}, 2024: {"A": (15, 11.0), "B": (5, 20.0)}})
    item = _item(_run(frame), "price_volume_mix")
    v = item.values
    assert v["total_change"] == pytest.approx(-420.0)
    assert v["volume_effect"] == pytest.approx(0.0, abs=1e-9)
    assert v["mix_effect"] == pytest.approx(-600.0)
    assert v["price_effect"] == pytest.approx(180.0)
    assert v["other_effect"] == pytest.approx(0.0)
    assert v["volume_effect"] + v["mix_effect"] + v["price_effect"] + v["other_effect"] == pytest.approx(
        v["total_change"]
    )


def test_a_segment_in_only_one_window_is_reported_on_its_own_line() -> None:
    frame = _monthly({2023: {"A": (10, 10.0)}, 2024: {"A": (10, 12.0), "C": (4, 5.0)}})
    item = _item(_run(frame), "price_volume_mix")
    v = item.values
    assert v["segments_in_one_window"] == 1
    assert v["other_effect"] == pytest.approx(12 * 4 * 5.0)  # all of C's revenue
    assert v["price_effect"] == pytest.approx(12 * 10 * 2.0)  # A: 120 units at +2
    assert v["volume_effect"] + v["mix_effect"] + v["price_effect"] + v["other_effect"] == pytest.approx(
        v["total_change"]
    )


def test_without_units_the_bridge_says_why_it_did_not_run() -> None:
    frame = _monthly({2023: {"A": (10, 10.0), "B": (10, 20.0)}, 2024: {"A": (15, 11.0), "B": (5, 20.0)}})
    result = _run(frame.drop(columns="units"))
    item = _item(result, "price_volume_mix")
    assert item.status == "not_run" and "units" in (item.reason or "")


# --- segment growth ------------------------------------------------------------------


def test_segment_growth_ranks_by_rate_and_leaves_out_a_tiny_base() -> None:
    # A +10%, B -20%, T is under 2% of the earlier total and doubles (not ranked).
    frame = _monthly(
        {2023: {"A": (10, 10.0), "B": (10, 10.0), "T": (0.1, 10.0)}, 2024: {"A": (11, 10.0), "B": (8, 10.0), "T": (0.2, 10.0)}}
    )
    item = _item(_run(frame), "segment_growth")
    v = item.values
    assert (v["fastest_segment"], v["slowest_segment"]) == ("A", "B")
    assert v["fastest_pct"] == pytest.approx(10.0)
    assert v["slowest_pct"] == pytest.approx(-20.0)
    assert v["segments_ranked"] == 2 and v["segments_left_out"] == 1
    assert v["spread_points"] == pytest.approx(30.0)


# --- customers -----------------------------------------------------------------------


def _orders(customer_values: list[str | None], amounts: list[float]) -> pd.DataFrame:
    months = pd.period_range("2023-01", "2024-12", freq="M")
    return pd.DataFrame(
        {
            "order_date": [months[i % len(months)].to_timestamp().date().isoformat() for i in range(len(amounts))],
            "customer_id": customer_values,
            "region": ["N" if i % 2 else "S" for i in range(len(amounts))],
            "revenue": amounts,
            "cost": [a * 0.5 for a in amounts],
        }
    )


def test_customer_view_top_share_and_rows_without_an_id() -> None:
    # 20 customers: c00 buys 800, the other 19 buy 10 each (190); 10 rows have no id.
    ids = ["c00"] * 8 + [f"c{i:02d}" for i in range(1, 20)] * 10 + [None] * 10
    amounts = [100.0] * 8 + [1.0] * 190 + [5.0] * 10
    frame = _orders(ids, amounts)
    item = _item(_run(frame), "customer_view")
    v = item.values
    assert v["customers"] == 20
    # top 10 = c00 (800) + nine customers at 10 each = 890 of 990 in the known rows
    assert v["top_n_share"] == pytest.approx(890 / 990)
    assert v["top_customer"] == "c00"
    assert v["rows_without_id_share"] == pytest.approx(10 / len(frame))
    assert "no customer_id" in item.sentence  # blanks are left out and said so


def test_a_numeric_customers_count_column_is_not_an_identifier() -> None:
    frame = _monthly({2023: {"A": (10, 10.0)}, 2024: {"A": (11, 10.0)}})
    frame["customers"] = np.arange(len(frame)) % 40 + 1
    result = _run(frame)
    assert not [i for i in result.items if i.kind == "customer_view"]


# --- seasonality on any 24 months ----------------------------------------------------


def test_seasonality_works_on_a_financial_year_table_with_growth() -> None:
    # April 2023 to March 2025 holds no two complete calendar years. December is 1.5x,
    # on top of 1% growth a month; the index must not mistake growth for a season.
    rows = []
    for i, month in enumerate(pd.period_range("2023-04", "2025-03", freq="M")):
        level = 1000 * 1.01**i * (1.5 if month.month == 12 else 1.0)
        for region in ("N", "S"):
            rows.append(
                {"month": month.to_timestamp().date().isoformat(), "region": region, "revenue": level / 2, "cost": level * 0.3}
            )
    item = _item(_run(pd.DataFrame(rows)), "seasonality")
    revenue = [i for i in _run(pd.DataFrame(rows)).items if i.id == "seasonality:revenue"][0]
    assert revenue.status == "ok"
    assert revenue.values["peak_month"] == 12
    assert revenue.values["peak_index"] > 1.35
    assert revenue.values["low_index"] > 0.85  # no other month stands out
    assert item.kind == "seasonality"


def test_seasonality_with_a_gap_uses_only_the_run_ending_at_the_latest_month() -> None:
    # 2022-01..03, then nothing until 2023-04: only the 24 months to 2025-03 are one run,
    # and they hold a single complete calendar year.
    months = list(pd.period_range("2022-01", "2022-03", freq="M")) + list(
        pd.period_range("2023-04", "2025-03", freq="M")
    )
    frame = pd.DataFrame(
        {
            "month": [m.to_timestamp().date().isoformat() for m in months for _ in ("N", "S")],
            "region": ["N", "S"] * len(months),
            "revenue": [500.0] * (2 * len(months)),
            "cost": [300.0] * (2 * len(months)),
        }
    )
    revenue = [i for i in _run(frame).items if i.id == "seasonality:revenue"][0]
    assert revenue.status == "ok"
    assert revenue.values["periods"] == 24
    assert revenue.values["peak_index"] == pytest.approx(1.0)  # a flat series has no season


# --- the story -----------------------------------------------------------------------


def _finance() -> ComputedAnalysis:
    frame = _monthly({2023: {"A": (10, 10.0), "B": (10, 20.0)}, 2024: {"A": (15, 11.0), "B": (5, 20.0)}})
    return _run(frame)


def test_the_story_leads_with_the_main_measure_and_lists_the_rest_as_also() -> None:
    result = _finance()
    story = result.story
    assert story is not None
    leads = [i for i in result.items if i.id in story.lead_ids]
    assert any(i.id == "period_change:revenue" for i in leads)
    assert "period_change:cost" not in story.lead_ids  # same story on another measure
    lead = next(i for i in result.items if i.id == "period_change:revenue")
    assert "period_change:cost" in lead.also


def test_the_story_never_drops_or_edits_a_figure() -> None:
    result = _finance()
    ids = [i.id for i in result.items]
    placed = {m for s in result.story.sections for m in s.item_ids}
    hidden = {m for i in result.items for m in i.also}
    assert set(ids) - placed - hidden <= {i.id for i in result.items if i.status == "not_run"}


def test_what_to_watch_questions_are_questions_tied_to_a_figure() -> None:
    result = _finance()
    ids = {i.id for i in result.items}
    assert result.story.questions
    for q in result.story.questions:
        assert q.text.endswith("?") and q.item_id in ids
    assert len(result.story.questions) <= load_computed_config().max_questions


def test_a_numeric_customer_id_prints_without_a_decimal() -> None:
    ids = [float(i % 25 + 1000) for i in range(300)]
    frame = _orders(ids, [10.0] * 300)
    item = _item(_run(frame), "customer_view")
    assert not any(str(r["customer"]).endswith(".0") for r in item.table)
