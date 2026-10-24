"""T4 (period change) and T6 (seasonality) through the whole gateway (P7)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.contracts.enums import ClaimType, Direction, GateOutcome, PermutationScheme, Verdict
from pramana.contracts.structure import DataStructure
from pramana.verification.gateway import verify_batch
from tests.fixtures.candidates import candidate
from tests.fixtures.config import load_pinned_config


@pytest.fixture(scope="module")
def config():
    shipped = load_pinned_config()
    return shipped.model_copy(
        update={"statistics": shipped.statistics.model_copy(update={"n_permutations": 999})}
    )


def _change(insight_id: str = "p1", time: str = "year"):
    return candidate(
        insight_id,
        "sales in the latest period tend to be higher than in the one before",
        ClaimType.PERIOD_CHANGE,
        [time, "sales"],
        direction=Direction.POSITIVE,
    )


def _season(insight_id: str = "s1"):
    return candidate(
        insight_id,
        "sales tend to differ by month of the year in this data",
        ClaimType.SEASONALITY,
        ["month", "sales"],
    )


def test_a_rise_across_the_same_regions_is_tested_paired(config) -> None:
    rng = np.random.default_rng(1)
    rows = []
    for e in range(20):
        base = rng.uniform(80, 120)
        for year in range(2019, 2025):
            bump = 1.12 if year == 2024 else 1.0
            rows.append({"year": year, "region": f"r{e}", "sales": base * bump + rng.normal(0, 2)})
    structure = DataStructure(
        shape="panel",
        time_column="year",
        entity_column="region",
        period="year",
        declared_by="shape_classifier",
    )
    proof = verify_batch([_change()], pd.DataFrame(rows), config, structure=structure)[0]
    assert proof.permutation_scheme is PermutationScheme.PAIRED
    assert proof.verdict is Verdict.PASS
    assert proof.effect_size == pytest.approx(0.12, abs=0.03)


def test_a_change_between_ledger_periods_is_tested_on_rows(config) -> None:
    rng = np.random.default_rng(2)
    months = np.repeat(pd.date_range("2024-01-01", periods=6, freq="MS"), 60)
    sales = rng.normal(100, 10, months.size) + np.where(months == months.max(), 15, 0)
    frame = pd.DataFrame({"month": months.astype(str), "sales": sales})
    structure = DataStructure(
        shape="transactions", time_column="month", period="month", declared_by="shape_classifier"
    )
    proof = verify_batch([_change(time="month")], frame, config, structure=structure)[0]
    assert proof.permutation_scheme is PermutationScheme.FREE
    assert proof.verdict is Verdict.PASS


def test_a_change_on_a_one_row_per_period_series_is_refused(config) -> None:
    frame = pd.DataFrame({"year": range(2000, 2030), "sales": np.arange(30.0)})
    structure = DataStructure(
        shape="time_series", time_column="year", period="year", declared_by="shape_classifier"
    )
    proof = verify_batch([_change()], frame, config, structure=structure)[0]
    assert proof.gate_outcome is GateOutcome.NOT_TESTABLE
    assert "one value per period" in (proof.failure_reason or "")


def test_a_season_is_found_in_two_years_of_months(config) -> None:
    rng = np.random.default_rng(3)
    months = pd.date_range("2021-01-01", periods=24, freq="MS")
    sales = 100 + 12 * np.sin(2 * np.pi * months.month / 12) + rng.normal(0, 2, 24)
    frame = pd.DataFrame({"month": months.astype(str), "sales": sales})
    structure = DataStructure(
        shape="time_series", time_column="month", period="month", declared_by="shape_classifier"
    )
    proof = verify_batch([_season()], frame, config, structure=structure)[0]
    assert proof.permutation_scheme is PermutationScheme.STRATIFIED
    assert proof.verdict is Verdict.PASS
    assert "CYCLE_LENGTH = 12" in (proof.falsification_code or "")


def test_one_year_of_months_is_too_few_for_a_season(config) -> None:
    months = pd.date_range("2024-01-01", periods=12, freq="MS")
    frame = pd.DataFrame({"month": months.astype(str), "sales": np.arange(12.0)})
    structure = DataStructure(
        shape="time_series", time_column="month", period="month", declared_by="shape_classifier"
    )
    proof = verify_batch([_season()], frame, config, structure=structure)[0]
    assert proof.gate_outcome is GateOutcome.NOT_TESTABLE
    assert "two years" in (proof.failure_reason or "")


def test_time_claims_on_a_table_without_time_are_refused(config) -> None:
    frame = pd.DataFrame({"year": np.arange(50.0), "sales": np.arange(50.0)})
    for claim in (_change(), _season()):
        proof = verify_batch([claim], frame, config)[0]
        assert proof.gate_outcome is GateOutcome.NOT_TESTABLE
