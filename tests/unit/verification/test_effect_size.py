"""Known-answer tests for the effect-size estimators.

Each metric is checked against a case whose answer is known analytically, plus a
reference implementation where scipy provides one.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats as scipy_stats

from pramana.verification.stats import effect_size as es

# --- association ----------------------------------------------------------


def test_perfect_monotone_relationship_gives_rho_one() -> None:
    x = np.arange(50, dtype=float)
    assert es.spearman_rho(x, x**3) == pytest.approx(1.0)
    assert es.spearman_rho(x, -(x**3)) == pytest.approx(-1.0)


def test_rho_matches_scipy() -> None:
    rng = np.random.default_rng(1)
    x, y = rng.normal(size=200), rng.normal(size=200)
    assert es.spearman_rho(x, y) == pytest.approx(float(scipy_stats.spearmanr(x, y).statistic))


def test_pearson_captures_linear_but_rho_captures_monotone() -> None:
    """The reason the gate uses rho: a strong non-linear monotone relationship is
    a real finding, and Pearson understates it."""
    x = np.arange(1, 60, dtype=float)
    y = np.exp(x / 10.0)
    assert es.spearman_rho(x, y) == pytest.approx(1.0)
    assert es.pearson_r(x, y) < 0.95


def test_outlier_divergence_flags_a_single_leverage_point() -> None:
    """One extreme point manufactures a large Pearson r out of pure noise. rho does
    not budge, and the divergence exposes it -- a free falsification signal."""
    rng = np.random.default_rng(2)
    x = np.concatenate([rng.normal(size=100), [50.0]])
    y = np.concatenate([rng.normal(size=100), [50.0]])
    assert es.pearson_r(x, y) > 0.9
    assert abs(es.spearman_rho(x, y)) < 0.3
    assert es.outlier_divergence(x, y) > 0.15


def test_constant_input_has_no_association() -> None:
    x = np.ones(20)
    rng = np.random.default_rng(3)
    assert es.spearman_rho(x, rng.normal(size=20)) == 0.0
    assert es.pearson_r(x, rng.normal(size=20)) == 0.0


# --- two-group difference -------------------------------------------------


def test_cliffs_delta_is_one_when_groups_do_not_overlap() -> None:
    assert es.cliffs_delta([10.0, 11.0, 12.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)
    assert es.cliffs_delta([1.0, 2.0, 3.0], [10.0, 11.0, 12.0]) == pytest.approx(-1.0)


def test_cliffs_delta_is_zero_for_identical_groups() -> None:
    sample = [1.0, 2.0, 3.0, 4.0]
    assert es.cliffs_delta(sample, sample) == pytest.approx(0.0)


def test_cliffs_delta_matches_mann_whitney_identity() -> None:
    """delta = 2U/(n_a*n_b) - 1. Cross-check the rank shortcut against scipy's U."""
    rng = np.random.default_rng(4)
    a, b = rng.normal(0.0, 1.0, 40), rng.normal(0.7, 1.0, 55)
    u = float(scipy_stats.mannwhitneyu(a, b, alternative="two-sided").statistic)
    assert es.cliffs_delta(a, b) == pytest.approx(2.0 * u / (a.size * b.size) - 1.0)


def test_hedges_g_recovers_a_planted_standardized_difference() -> None:
    rng = np.random.default_rng(5)
    a = rng.normal(0.0, 1.0, 4000)
    b = rng.normal(0.8, 1.0, 4000)
    assert es.hedges_g(a, b) == pytest.approx(-0.8, abs=0.08)


def test_hedges_g_is_smaller_in_magnitude_than_cohens_d() -> None:
    """The small-sample correction always shrinks the estimate; it is free, so raw
    Cohen's d is never the better choice."""
    a, b = [1.0, 2.0, 3.0, 4.0, 9.0], [5.0, 6.0, 7.0, 8.0, 14.0]
    pooled = math.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2.0)
    cohens_d = (np.mean(a) - np.mean(b)) / pooled
    assert abs(es.hedges_g(a, b)) < abs(cohens_d)


# --- k-group --------------------------------------------------------------


def test_epsilon_squared_is_near_zero_under_the_null() -> None:
    rng = np.random.default_rng(6)
    groups = [rng.normal(size=200) for _ in range(4)]
    assert es.epsilon_squared(groups) < 0.05


def test_epsilon_squared_grows_with_separation() -> None:
    rng = np.random.default_rng(7)
    close = [rng.normal(0.0, 1.0, 150), rng.normal(0.2, 1.0, 150), rng.normal(0.4, 1.0, 150)]
    far = [rng.normal(0.0, 1.0, 150), rng.normal(3.0, 1.0, 150), rng.normal(6.0, 1.0, 150)]
    assert es.epsilon_squared(close) < es.epsilon_squared(far)
    assert es.epsilon_squared(far) > 0.5


def test_eta_squared_is_bounded() -> None:
    rng = np.random.default_rng(8)
    groups = [rng.normal(0.0, 1.0, 100), rng.normal(5.0, 1.0, 100)]
    assert 0.0 <= es.eta_squared(groups) <= 1.0


# --- trend ----------------------------------------------------------------


def test_kendall_tau_matches_scipy() -> None:
    rng = np.random.default_rng(9)
    x, y = rng.normal(size=150), rng.normal(size=150)
    reference = float(scipy_stats.kendalltau(x, y, variant="b").statistic)
    assert es.kendall_tau_b(x, y) == pytest.approx(reference)


def test_tau_runs_smaller_than_rho_for_the_same_relationship() -> None:
    """The empirical basis for calibrating trend thresholds separately:
    tau ~ (2/pi) * arcsin(rho)."""
    rng = np.random.default_rng(10)
    x = rng.normal(size=3000)
    y = 0.5 * x + rng.normal(size=3000)
    rho, tau = es.spearman_rho(x, y), es.kendall_tau_b(x, y)
    assert tau < rho
    assert tau == pytest.approx((2.0 / math.pi) * math.asin(rho), abs=0.03)


def test_sens_slope_recovers_the_planted_slope_in_original_units() -> None:
    x = np.arange(100, dtype=float)
    y = 0.4 * x + 5.0
    assert es.sens_slope(x, y) == pytest.approx(0.4)


def test_sens_slope_resists_outliers() -> None:
    """Theil-Sen is why the slope is trustworthy enough to print in a report."""
    x = np.arange(60, dtype=float)
    y = 0.4 * x + 5.0
    y[30] = 5000.0
    assert es.sens_slope(x, y) == pytest.approx(0.4, abs=0.05)


# --- categorical ----------------------------------------------------------


def test_cramers_v_is_zero_for_independent_table() -> None:
    table = [[25, 25], [25, 25]]
    assert es.cramers_v(table) == pytest.approx(0.0)


def test_cramers_v_is_one_for_perfect_association() -> None:
    table = [[50, 0], [0, 50]]
    assert es.cramers_v(table) == pytest.approx(1.0)


def test_table_k_is_the_smaller_dimension() -> None:
    assert es.table_k([[1, 2, 3], [4, 5, 6]]) == 2
    assert es.table_k([[1, 2], [3, 4], [5, 6]]) == 2


# --- degenerate input -----------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda: es.spearman_rho([1.0, 2.0], [1.0, 2.0]),
        lambda: es.kendall_tau_b([1.0, 2.0], [1.0, 2.0]),
        lambda: es.sens_slope([1.0, 2.0], [1.0, 2.0]),
        lambda: es.cliffs_delta([], [1.0]),
        lambda: es.hedges_g([1.0], [2.0]),
        lambda: es.epsilon_squared([[1.0, 2.0, 3.0]]),
        lambda: es.cramers_v([[1, 2, 3]]),
    ],
)
def test_degenerate_input_raises(call: object) -> None:
    with pytest.raises(ValueError):
        call()  # type: ignore[operator]
