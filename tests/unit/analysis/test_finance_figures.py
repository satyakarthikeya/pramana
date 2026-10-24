"""Exact tier on a financial-year table: margins, single-row outliers and FY names (F4-F6)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.analysis import infer_schema, load_config
from pramana.analysis.computed import ComputedAnalysis, compute_analysis


def _table(spike: bool = True, fiscal_column: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    rows = []
    for month in pd.period_range("2023-04", "2025-03", freq="M"):
        year = month.year + 1 if month.month >= 4 else month.year
        for region in ("North", "South", "East"):
            for product, ratio in (("Core", 0.60), ("Lite", 0.70 if year == 2025 else 0.60)):
                revenue = 1000.0 * rng.uniform(0.9, 1.1) * (2 if region == "South" else 1)
                rows.append(
                    {
                        "month": month.to_timestamp().date().isoformat(),
                        "fiscal_year": f"FY{year}",
                        "region": region,
                        "product": product,
                        "revenue": revenue,
                        "cost": revenue * ratio,
                    }
                )
    frame = pd.DataFrame(rows)
    if spike:
        frame.loc[40, "revenue"] *= 8
    return frame if fiscal_column else frame.drop(columns="fiscal_year")


def _run(frame: pd.DataFrame) -> ComputedAnalysis:
    return compute_analysis(frame, infer_schema(frame, load_config().schema_inference))


def _one(result: ComputedAnalysis, item_id_prefix: str):
    found = [i for i in result.items if i.id.startswith(item_id_prefix)]
    assert found, [i.id for i in result.items]
    return found[0]


def test_margin_falls_and_the_segment_that_caused_it_is_named() -> None:
    result = _run(_table(spike=False))
    item = _one(result, "margins:revenue:cost")
    assert item.status == "ok"
    # Core keeps a 40% margin; Lite goes from 40% to 30%; half the rows are Lite.
    assert item.values["margin_before_pct"] == pytest.approx(40.0, abs=1e-6)
    assert item.values["margin_now_pct"] == pytest.approx(35.0, abs=0.1)
    assert item.values["change_points"] == pytest.approx(-5.0, abs=0.1)
    assert "down 5.0 points" in item.sentence or "down 4.9 points" in item.sentence
    assert "product = Lite" in item.sentence
    worst = item.table[0]
    assert (worst["column"], worst["level"]) == ("product", "Lite")
    assert worst["change_points"] == pytest.approx(-10.0, abs=1e-6)


def test_windows_use_the_tables_own_fiscal_year_labels() -> None:
    item = _one(_run(_table(spike=False)), "margins:revenue:cost")
    assert "FY2025 (2024-04 to 2025-03)" in item.sentence
    assert "FY2024 (2023-04 to 2024-03)" in item.sentence


def test_without_a_fiscal_column_the_windows_keep_the_calendar_wording() -> None:
    item = _one(_run(_table(spike=False, fiscal_column=False)), "margins:revenue:cost")
    assert "the 12 months to 2025-03" in item.sentence
    assert "FY2025" not in item.sentence


def test_a_single_inflated_row_is_listed_even_when_period_totals_hide_it() -> None:
    result = _run(_table(spike=True))
    item = _one(result, "row_outliers:revenue")
    assert item.values["flagged"] >= 1
    assert item.table[0]["where"].startswith("row 41 (")
    assert item.table[0]["times_median"] > 5
    assert "row 41" in item.sentence


def test_a_clean_table_flags_no_single_row() -> None:
    item = _one(_run(_table(spike=False)), "row_outliers:revenue")
    assert item.values["flagged"] == 0
    assert item.table == []


def test_a_sector_entity_column_with_many_levels_is_still_the_group() -> None:
    rng = np.random.default_rng(5)
    rows = []
    countries = [f"country_{i:02d}" for i in range(43)]
    for month in pd.period_range("2022-01", "2023-12", freq="M"):
        for i, country in enumerate(countries):
            if rng.random() < 0.7:
                rows.append(
                    {
                        "month": month.to_timestamp().date().isoformat(),
                        "country": country,
                        "revenue": 1000.0 * (1 + i / 10) * rng.uniform(0.8, 1.2),
                        "orders": int(rng.integers(5, 50)),
                    }
                )
    result = _run(pd.DataFrame(rows))
    assert result.shape.entity_column == "country"
    assert any(i.kind == "variance_decomposition" for i in result.items)
    assert any(i.kind == "concentration" for i in result.items)
