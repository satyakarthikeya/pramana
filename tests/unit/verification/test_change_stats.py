"""Known answers and calibration for the period-change and seasonality tests (P7)."""

from __future__ import annotations

import numpy as np
import pytest

from pramana.contracts.enums import PermutationScheme
from pramana.verification.stats.change import (
    period_change_test_groups,
    period_change_test_paired,
    relative_change,
    seasonality_test,
)

TRIALS, B, ALPHA = 200, 99, 0.05
UPPER = ALPHA + 3.5 * np.sqrt(ALPHA * (1 - ALPHA) / TRIALS)


def _months(years: int) -> tuple[np.ndarray, np.ndarray]:
    index = np.arange(12 * years)
    return index % 12, index // 12


def test_relative_change_known_answer_and_zero_base() -> None:
    assert relative_change([100, 100], [110, 110]) == pytest.approx(0.10)
    assert relative_change([-50], [-25]) == pytest.approx(0.5)
    with pytest.raises(ValueError, match="zero"):
        relative_change([0, 0], [1, 1])


def test_a_real_rise_across_entities_is_found_and_stamped_paired() -> None:
    rng = np.random.default_rng(1)
    before = rng.normal(100, 10, size=30)
    after = before * 1.08 + rng.normal(0, 2, size=30)
    result = period_change_test_paired(before, after, n_permutations=999, seed=1)
    assert result.p_value < 0.01 and result.statistic == pytest.approx(
        (after - before).mean() / before.mean()
    )
    assert result.scheme is PermutationScheme.PAIRED


def test_a_rise_between_ledger_periods_is_found() -> None:
    rng = np.random.default_rng(2)
    result = period_change_test_groups(
        rng.normal(100, 15, 200), rng.normal(112, 15, 220), n_permutations=999, seed=2
    )
    assert result.p_value < 0.01 and result.statistic > 0.05
    assert result.scheme is PermutationScheme.FREE


def test_a_yearly_cycle_is_a_season_and_a_trend_is_not() -> None:
    rng = np.random.default_rng(3)
    cycle, year = _months(4)
    peak = 100 + 10 * np.sin(2 * np.pi * cycle / 12) + rng.normal(0, 3, cycle.size)
    found = seasonality_test(peak, cycle, year, n_permutations=999, seed=3)
    assert found.p_value < 0.01 and found.scheme is PermutationScheme.STRATIFIED
    trend_only = 100 + 15 * year + rng.normal(0, 3, cycle.size)
    assert seasonality_test(trend_only, cycle, year, n_permutations=999, seed=3).p_value > 0.05


def test_seasonality_refuses_a_single_year() -> None:
    cycle, year = _months(1)
    with pytest.raises(ValueError, match="two years"):
        seasonality_test(np.arange(12.0), cycle, year, n_permutations=99, seed=1)


@pytest.mark.slow
def test_change_and_season_nulls_are_calibrated() -> None:
    paired = groups = season = 0
    cycle, year = _months(3)
    for t in range(TRIALS):
        rng = np.random.default_rng(5000 + t)
        level = rng.normal(100, 10, 25)
        paired += (
            period_change_test_paired(
                level + rng.normal(0, 5, 25), level + rng.normal(0, 5, 25), n_permutations=B, seed=t
            ).p_value
            < ALPHA
        )
        groups += (
            period_change_test_groups(
                rng.normal(100, 10, 60), rng.normal(100, 10, 60), n_permutations=B, seed=t
            ).p_value
            < ALPHA
        )
        noise = 100 + 10 * year + rng.normal(0, 3, cycle.size)
        season += seasonality_test(noise, cycle, year, n_permutations=B, seed=t).p_value < ALPHA
    for name, hits in (("paired", paired), ("groups", groups), ("season", season)):
        assert hits / TRIALS <= UPPER, f"{name} FPR {hits / TRIALS:.3f} exceeds {UPPER:.3f}"
