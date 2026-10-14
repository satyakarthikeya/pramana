"""Known-answer tests for the permutation test (AGENTS.md 3, SCOPE.md 4 step 2).

The calibration test below is the single most important test in the repository:
it demonstrates that the gate's false-positive rate is what it claims to be.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats as scipy_stats

from pramana.verification.stats import permutation_test, permutation_test_groups
from pramana.verification.stats.effect_size import cliffs_delta, spearman_rho


def _rho(a: np.ndarray, b: np.ndarray) -> float:
    return spearman_rho(a, b)


def test_planted_effect_yields_small_p() -> None:
    rng = np.random.default_rng(11)
    x = rng.normal(size=300)
    y = 0.8 * x + rng.normal(size=300)
    result = permutation_test(x, y, _rho, n_permutations=2000, seed=7)
    assert result.p_value < 0.001
    assert result.statistic > 0.5


def test_planted_null_yields_large_p() -> None:
    rng = np.random.default_rng(12)
    x = rng.normal(size=300)
    y = rng.normal(size=300)
    result = permutation_test(x, y, _rho, n_permutations=2000, seed=7)
    assert result.p_value > 0.05


@pytest.mark.slow
def test_null_calibration_false_positive_rate() -> None:
    """Under a true null, p must be uniform: p < 0.05 fires about 5% of the time.

    This is what licenses the FDR claim. If this test fails, every verdict the
    gateway issues is untrustworthy no matter how correct the rest of the code is.
    """
    n_trials = 300
    hits = 0
    for trial in range(n_trials):
        rng = np.random.default_rng(1000 + trial)
        x = rng.normal(size=60)
        y = rng.normal(size=60)
        result = permutation_test(x, y, _rho, n_permutations=400, seed=trial)
        hits += result.p_value < 0.05
    rate = hits / n_trials
    # Binomial(300, 0.05) has sd ~ 0.0126; +-3.5 sd keeps this from flaking.
    assert 0.006 < rate < 0.094, f"false-positive rate {rate:.3f} is off nominal 0.05"


def test_same_seed_reproduces_exactly() -> None:
    rng = np.random.default_rng(13)
    x, y = rng.normal(size=100), rng.normal(size=100)
    first = permutation_test(x, y, _rho, n_permutations=500, seed=42)
    second = permutation_test(x, y, _rho, n_permutations=500, seed=42)
    assert first.p_value == second.p_value
    assert first.statistic == second.statistic


def test_different_seeds_differ_but_agree_roughly() -> None:
    rng = np.random.default_rng(14)
    x, y = rng.normal(size=100), rng.normal(size=100)
    a = permutation_test(x, y, _rho, n_permutations=500, seed=1)
    b = permutation_test(x, y, _rho, n_permutations=500, seed=2)
    assert a.statistic == b.statistic  # observed statistic does not depend on the seed
    assert abs(a.p_value - b.p_value) < 0.15


def test_p_value_is_never_zero_and_respects_its_floor() -> None:
    """A permutation test cannot resolve finer than 1/(B+1). It must not pretend to."""
    x = np.arange(200, dtype=float)
    y = x * 3.0  # perfect monotone relationship: nothing can beat it
    result = permutation_test(x, y, _rho, n_permutations=1000, seed=5)
    assert result.p_value == pytest.approx(1.0 / 1001.0)
    assert result.p_value > 0.0
    assert result.p_value >= result.p_value_floor


def test_agrees_with_scipy_on_clean_gaussian_data() -> None:
    """Cross-check against an independent implementation on data where both are valid."""
    rng = np.random.default_rng(15)
    x = rng.normal(size=400)
    y = 0.35 * x + rng.normal(size=400)
    ours = permutation_test(x, y, _rho, n_permutations=4000, seed=3)
    reference = scipy_stats.spearmanr(x, y)
    assert ours.statistic == pytest.approx(float(reference.statistic))
    assert ours.p_value < 0.01 and reference.pvalue < 0.01


def test_one_sided_alternatives_split_the_evidence() -> None:
    rng = np.random.default_rng(16)
    x = rng.normal(size=200)
    y = 0.5 * x + rng.normal(size=200)
    greater = permutation_test(x, y, _rho, n_permutations=1000, seed=4, alternative="greater")
    less = permutation_test(x, y, _rho, n_permutations=1000, seed=4, alternative="less")
    assert greater.p_value < 0.01
    assert less.p_value > 0.99


def test_group_permutation_detects_real_difference() -> None:
    rng = np.random.default_rng(17)
    groups = [rng.normal(0.0, 1.0, 120), rng.normal(1.2, 1.0, 120)]
    result = permutation_test_groups(
        groups, lambda gs: cliffs_delta(gs[0], gs[1]), n_permutations=1000, seed=8
    )
    assert result.p_value < 0.01
    assert result.statistic < -0.4  # group 0 sits below group 1


def test_group_permutation_accepts_the_null() -> None:
    rng = np.random.default_rng(18)
    groups = [rng.normal(0.0, 1.0, 120), rng.normal(0.0, 1.0, 120)]
    result = permutation_test_groups(
        groups, lambda gs: cliffs_delta(gs[0], gs[1]), n_permutations=1000, seed=8
    )
    assert result.p_value > 0.05


@pytest.mark.parametrize(
    ("x", "y"),
    [
        ([1.0, 2.0], [1.0, 2.0]),  # fewer than 3 observations
        ([1.0, 2.0, 3.0], [1.0, 2.0]),  # mismatched shapes
    ],
)
def test_rejects_degenerate_input(x: list[float], y: list[float]) -> None:
    with pytest.raises(ValueError):
        permutation_test(x, y, _rho, n_permutations=100, seed=1)


def test_constant_column_is_not_a_finding() -> None:
    """A column with no variance carries no association. It must not sneak a low p."""
    x = np.ones(50)
    rng = np.random.default_rng(19)
    y = rng.normal(size=50)
    result = permutation_test(x, y, _rho, n_permutations=500, seed=1)
    assert result.statistic == 0.0
    assert result.p_value == 1.0


# --- characterization: the "can this be computed at all" floor ------------


def test_permutation_test_floor_is_three_paired_observations() -> None:
    with pytest.raises(ValueError, match="below the minimum of 3"):
        permutation_test([1.0, 2.0], [1.0, 2.0], _rho, n_permutations=50, seed=1)
    for n in (3, 4):
        x = [float(i) for i in range(n)]
        y = [float(i % 2) + 0.1 * i for i in range(n)]
        result = permutation_test(x, y, _rho, n_permutations=50, seed=1)
        assert 0.0 < result.p_value <= 1.0


def test_group_permutation_floor_is_set_by_group_size_not_the_total() -> None:
    """Every group needs 2 rows, so two groups already total 4 and the pooled floor of 3
    can never be what stops a run."""
    with pytest.raises(ValueError, match="at least 2 observations"):
        permutation_test_groups(
            [[1.0, 2.0], [3.0]], cliffs_delta, n_permutations=50, seed=1
        )
    result = permutation_test_groups(
        [[1.0, 2.0], [3.0, 4.0]],
        lambda g: cliffs_delta(g[0], g[1]),
        n_permutations=50,
        seed=1,
    )
    assert 0.0 < result.p_value <= 1.0


def test_every_template_receives_the_configured_floor_not_the_stats_floor() -> None:
    """Each rendered falsification module carries `statistics.min_observations` verbatim."""
    from pramana.verification.falsification.generator import generate_from_template
    from tests.fixtures.candidates import TESTABLE_CANDIDATES
    from tests.fixtures.config import load_pinned_config

    config = load_pinned_config()
    assert config.statistics.min_observations != 3
    for candidate in TESTABLE_CANDIDATES:
        source = generate_from_template(candidate, config).source
        assert f"MIN_OBSERVATIONS = {config.statistics.min_observations}\n" in source
        assert "MIN_OBSERVATIONS = 3\n" not in source
