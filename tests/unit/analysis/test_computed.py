"""Exact tier (PLAN §5.1, §14): known answers on hand-built tables, wording, failures."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from pramana.analysis import infer_schema, load_config
from pramana.analysis.computed import ComputedAnalysis, ExactItem, compute_analysis
from pramana.verification.admissibility import CAUSAL_TERMS, UNIVERSAL_TERMS, _matched_terms
from tests.unit.analysis import computed_fixtures as fx


def _run(frame: pd.DataFrame, **kwargs) -> ComputedAnalysis:
    return compute_analysis(frame, infer_schema(frame, load_config().schema_inference), **kwargs)


def _item(result: ComputedAnalysis, kind: str, column: str | None = None) -> ExactItem:
    found = [
        item
        for item in result.items
        if item.kind == kind and (column is None or column in item.columns)
    ]
    assert found, f"no {kind} item for {column}: {[i.id for i in result.items]}"
    return found[0]


@pytest.fixture(scope="module")
def finance() -> ComputedAnalysis:
    return _run(fx.finance_year())


def test_finance_run_records_sector_and_shape(finance: ComputedAnalysis) -> None:
    assert finance.sector.sector == "finance"
    assert finance.shape.shape.value == "panel"


def test_period_change_latest_month(finance: ComputedAnalysis) -> None:
    item = _item(finance, "period_change", "revenue")
    assert item.status == "ok"
    dec, nov = fx.revenue_total(11), fx.revenue_total(10)
    assert item.values["current"] == pytest.approx(dec)
    assert item.values["previous"] == pytest.approx(nov)
    assert item.values["change"] == pytest.approx(dec - nov)
    assert item.values["change_pct"] == pytest.approx(100 * (dec - nov) / nov)
    assert item.formula and item.n_rows == 8


def test_variance_decomposition_names_the_region_that_accounts_for_the_change(
    finance: ComputedAnalysis,
) -> None:
    item = _item(finance, "variance_decomposition", "revenue")
    shares = {row["segment"]: row["share_of_change"] for row in item.table}
    assert shares["North"] == pytest.approx(10 / 13)
    assert sum(shares.values()) == pytest.approx(1.0)
    assert item.values["top_segment"] == "North"


def test_concentration_of_revenue_by_region(finance: ComputedAnalysis) -> None:
    item = _item(finance, "concentration", "revenue")
    north = 12 * 100 + 10 * sum(range(12))
    total = sum(12 * b + fx.REGION_STEP[r] * sum(range(12)) for r, b in fx.REGION_BASE.items())
    assert item.values["top_segment"] == "North"
    assert item.values["top_share"] == pytest.approx(north / total)


def test_segment_ranking_orders_regions(finance: ComputedAnalysis) -> None:
    item = _item(finance, "segment_ranking", "revenue")
    assert [row["segment"] for row in item.table] == ["North", "South", "East", "West"]


def test_cost_spike_is_flagged_in_march(finance: ComputedAnalysis) -> None:
    item = _item(finance, "outliers", "cost")
    assert item.status == "ok"
    assert any(str(row["where"]).startswith("2025-03") for row in item.table)


def test_seasonality_refuses_a_single_year(finance: ComputedAnalysis) -> None:
    item = _item(finance, "seasonality")
    assert item.status == "not_run"
    assert "2 full" in (item.reason or "")


def test_seasonality_finds_the_december_peak() -> None:
    item = _item(_run(fx.finance_two_years()), "seasonality", "revenue")
    assert item.status == "ok"
    assert item.values["peak_month"] == 12
    mean = (11 * 200 + 300) / 12
    assert item.values["peak_index"] == pytest.approx(300 / mean)


def test_accounting_identity_is_reported(finance: ComputedAnalysis) -> None:
    item = _item(finance, "identity")
    assert set(item.columns) == {"profit", "revenue", "cost"}


def test_health_prevalence_is_weighted_when_weights_exist() -> None:
    result = _run(fx.health_sample())
    item = _item(result, "prevalence", "BMXBMI")
    expected = (
        fx.N_OBESE
        * fx.OBESE_WEIGHT
        / (fx.N_OBESE * fx.OBESE_WEIGHT + (fx.N_HEALTH - fx.N_OBESE) * fx.OTHER_WEIGHT)
    )
    assert item.values["share"] == pytest.approx(expected)
    assert item.values["weighted"] is True
    assert "WTMEC2YR" in item.columns
    assert "weighted" in item.sentence


def test_health_prevalence_without_weights_says_it_is_a_sample_share() -> None:
    item = _item(_run(fx.health_sample(with_weights=False)), "prevalence", "BMXBMI")
    assert item.values["share"] == pytest.approx(fx.N_OBESE / fx.N_HEALTH)
    assert item.values["weighted"] is False
    assert "this sample" in item.sentence
    assert "not a population estimate" in item.sentence


def test_health_prevalence_has_a_breakdown_by_sex() -> None:
    item = _item(_run(fx.health_sample()), "prevalence", "BMXBMI")
    assert {row["group"] for row in item.table} >= {"Male", "Female"}


def test_health_never_groups_by_a_respondent_id_or_sums_a_clinical_measure() -> None:
    result = _run(fx.health_sample())
    grouped = [i for i in result.items if i.kind != "data_quality"]  # it lists every column checked
    assert not any("SEQN" in item.columns for item in grouped)
    assert not any(item.kind in {"concentration", "period_change"} for item in result.items)


@pytest.mark.parametrize(
    "build",
    [
        fx.finance_year,
        fx.finance_two_years,
        fx.health_sample,
        fx.transactions,
        fx.cross_section,
        fx.time_series,
    ],
)
def test_no_sentence_uses_causal_or_universal_wording(build) -> None:
    for item in _run(build()).items:
        text = f"{item.title} {item.sentence} {item.reason or ''}"
        assert not _matched_terms(text, CAUSAL_TERMS), (item.id, text)
        assert not _matched_terms(text, UNIVERSAL_TERMS), (item.id, text)


@pytest.mark.parametrize("build", [fx.finance_year, fx.health_sample, fx.cross_section])
def test_every_item_shows_its_work(build) -> None:
    for item in _run(build()).items:
        assert item.level == "exact"
        if item.status == "ok":
            assert item.formula and item.columns and item.n_rows > 0, item.id
            assert all(
                not isinstance(v, float) or math.isfinite(v) for v in item.values.values()
            ), item.id
        else:
            assert item.reason, item.id


def test_one_failing_analysis_does_not_hide_the_others(monkeypatch) -> None:
    from pramana.analysis.computed import runner

    def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setitem(runner.ANALYSES, "concentration", broken)
    result = _run(fx.finance_year())
    failed = [i for i in result.items if i.kind == "concentration"]
    assert failed and failed[0].status == "not_run" and failed[0].reason
    assert "boom" not in failed[0].reason  # internal text never reaches the user
    assert any(i.kind == "period_change" and i.status == "ok" for i in result.items)


def test_same_input_gives_identical_output() -> None:
    a = _run(fx.finance_year()).model_dump_json()
    b = _run(fx.finance_year()).model_dump_json()
    assert a == b


def test_no_model_facing_module_reads_the_exact_tier() -> None:
    """D5: full-table figures go to the user, never to the proposer, agent, chat or advisory."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "src" / "pramana"
    model_facing = [
        "chat",
        "analysis/workspace",
        "analysis/hypotheses",
        "advisory",
        "orchestration",
        "verification",
        "memory",
    ]
    for folder in model_facing:
        for path in (root / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            # chat holds the DatasetView for its brief; it must never read `.computed`
            assert "analysis.computed" not in text and ".computed" not in text, path


def test_sector_override_is_recorded() -> None:
    result = _run(fx.finance_year(), sector="general")
    assert result.sector.sector == "general"


# --- report polish: outlier wording and incomplete last period ------------------------


def test_row_outlier_with_zero_median_never_reads_as_a_ratio() -> None:
    from pramana.analysis.computed.runner import _against_median

    text = _against_median(1.0, 500.0, 0.0, "their country median", -6.2)
    assert "times" not in text and "0.0" not in text
    assert "6.2 robust deviations below" in text
    assert "typical non-zero value" in text
    assert _against_median(900.0, 300.0, 300.0, "their country median", 4.0) == (
        "3.0 times their country median."
    )


def _daily(last_day: int) -> pd.DataFrame:
    days = pd.date_range("2025-01-01", f"2025-08-{last_day:02d}", freq="D")
    return pd.DataFrame(
        {
            "date": days.strftime("%Y-%m-%d"),
            "region": ["North", "South"] * (len(days) // 2) + ["North"] * (len(days) % 2),
            "revenue": 100.0 + (days.dayofyear % 7),
            "cost": 60.0 + (days.dayofyear % 5),
        }
    )


def test_partial_last_month_is_flagged_not_dropped() -> None:
    result = _run(_daily(9))
    change = _item(result, "period_change", "revenue")
    assert "2025-08" in str(change.values["current_label"])
    assert "looks incomplete" in change.sentence
    assert "read with care" in change.sentence
    quality = _item(result, "data_quality")
    assert any(r["check"] == "incomplete last period" for r in quality.table)


def test_complete_last_month_is_not_flagged() -> None:
    result = _run(_daily(31))
    assert "looks incomplete" not in _item(result, "period_change", "revenue").sentence
    quality = _item(result, "data_quality")
    assert not any(r["check"] == "incomplete last period" for r in quality.table)


def test_month_stamped_on_the_first_is_not_flagged() -> None:
    result = _run(fx.finance_year())
    assert "looks incomplete" not in _item(result, "period_change", "revenue").sentence
