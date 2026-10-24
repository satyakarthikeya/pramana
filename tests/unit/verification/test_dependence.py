"""Known-answer and calibration tests for the dependence-aware nulls (PLAN D6, P1).

Each calibration test runs the same null twice: once with today's free shuffle, which
must be badly miscalibrated on that kind of data (the bug P1 fixes), and once with the
dependence-aware test, whose false-positive rate must sit near alpha.
"""

from __future__ import annotations

import numpy as np
import pytest

from pramana.contracts.enums import PermutationScheme
from pramana.verification.stats import (
    cliffs_delta,
    correlation_test_differenced,
    default_block_length,
    kendall_tau_b,
    lag1_autocorrelation,
    permutation_test,
    permutation_test_groups,
    permutation_test_groups_clustered,
    permutation_test_groups_stratified,
    permutation_test_stratified,
    spearman_rho,
    trend_test_differenced,
)

B = 99  # resolves p to 0.01, enough to count p < 0.05
TRIALS = 200
ALPHA = 0.05
#: Binomial(200, 0.05) has sd ~0.0154; 3.5 sd above nominal keeps these from flaking.
UPPER = ALPHA + 3.5 * np.sqrt(ALPHA * (1 - ALPHA) / TRIALS)
#: A free shuffle on dependent data should be far worse than this.
BROKEN = 0.25


def _delta(parts: list[np.ndarray]) -> float:
    return cliffs_delta(parts[0], parts[1])


def _random_walk(rng: np.random.Generator, n: int) -> np.ndarray:
    return np.cumsum(rng.normal(size=n))


# --- known answers ---------------------------------------------------------


def test_block_length_grows_with_the_cube_root() -> None:
    assert default_block_length(1) == 1
    assert default_block_length(27) == 3
    assert default_block_length(60) == 4


def test_lag1_autocorrelation_known_answers() -> None:
    assert lag1_autocorrelation([1.0, 1.0, 1.0, 1.0]) == 0.0
    assert lag1_autocorrelation([1.0, -1.0] * 20) < -0.9
    rng = np.random.default_rng(3)
    assert abs(lag1_autocorrelation(rng.normal(size=2000))) < 0.06
    assert lag1_autocorrelation(_random_walk(rng, 500)) > 0.9


def test_a_drift_is_found_and_stamped_as_block_differenced() -> None:
    rng = np.random.default_rng(5)
    series = np.cumsum(0.8 + rng.normal(size=60))
    result = trend_test_differenced(
        np.arange(60), series, block_length=4, n_permutations=999, seed=1
    )
    assert result.p_value < 0.01
    assert result.statistic == kendall_tau_b(np.arange(60), series)
    assert result.scheme is PermutationScheme.BLOCK_DIFFERENCED


def test_the_trend_test_sorts_by_time_and_refuses_repeated_time_points() -> None:
    rng = np.random.default_rng(6)
    series = np.cumsum(1.0 + rng.normal(size=40))
    time = np.arange(40)
    shuffled = rng.permutation(40)
    a = trend_test_differenced(time, series, block_length=3, n_permutations=199, seed=2)
    b = trend_test_differenced(
        time[shuffled], series[shuffled], block_length=3, n_permutations=199, seed=2
    )
    assert a.p_value == b.p_value and a.statistic == b.statistic
    with pytest.raises(ValueError, match="repeats"):
        trend_test_differenced(
            np.r_[time[:-1], 0], series, block_length=3, n_permutations=199, seed=2
        )


def test_series_that_change_together_are_found() -> None:
    rng = np.random.default_rng(7)
    shared = rng.normal(size=80)
    x = np.cumsum(shared + 0.3 * rng.normal(size=80))
    y = np.cumsum(shared + 0.3 * rng.normal(size=80))
    result = correlation_test_differenced(
        np.arange(80), x, y, block_length=4, n_permutations=999, seed=3
    )
    assert result.p_value < 0.01
    assert result.scheme is PermutationScheme.BLOCK_DIFFERENCED


def test_stratified_values_never_leave_their_stratum() -> None:
    strata = np.repeat(np.arange(5), 6)
    x = np.arange(30, dtype=float)
    seen: list[np.ndarray] = []

    def spy(left: np.ndarray, right: np.ndarray) -> float:
        seen.append(right.copy())
        return 0.0

    permutation_test_stratified(x, x.copy(), strata, spy, n_permutations=50, seed=4)
    for draw in seen:
        for s in range(5):
            assert set(draw[strata == s]) == set(x[strata == s])


def test_cluster_labels_move_with_their_whole_entity() -> None:
    clusters = np.repeat(np.arange(8), 5)
    labels = np.where(clusters < 4, "a", "b")
    values = np.arange(40, dtype=float)
    seen: list[list[np.ndarray]] = []

    def spy(parts: list[np.ndarray]) -> float:
        seen.append(parts)
        return 0.0

    result = permutation_test_groups_clustered(
        values, labels, clusters, spy, order=["a", "b"], n_permutations=50, seed=5
    )
    assert result.scheme is PermutationScheme.CLUSTER
    for parts in seen:
        for part in parts:  # each group holds whole entities only
            owners = set(clusters[np.isin(values, part)])
            assert sum((clusters == c).sum() for c in owners) == part.size


def test_a_label_that_varies_within_an_entity_is_refused() -> None:
    clusters = np.repeat(np.arange(6), 4)
    labels = np.tile(["a", "b"], 12)
    with pytest.raises(ValueError, match="varies within one entity"):
        permutation_test_groups_clustered(
            np.arange(24.0),
            labels,
            clusters,
            _delta,
            order=["a", "b"],
            n_permutations=10,
            seed=1,
        )


def test_a_stratum_with_one_label_each_is_refused() -> None:
    strata = np.repeat(np.arange(6), 4)
    labels = np.where(strata < 3, "a", "b")
    with pytest.raises(ValueError, match="no stratum holds two different labels"):
        permutation_test_groups_stratified(
            np.arange(24.0),
            labels,
            strata,
            _delta,
            order=["a", "b"],
            n_permutations=10,
            seed=1,
        )


def test_dependence_aware_tests_are_reproducible() -> None:
    rng = np.random.default_rng(8)
    series = _random_walk(rng, 50)
    first = trend_test_differenced(
        np.arange(50), series, block_length=4, n_permutations=300, seed=11
    )
    second = trend_test_differenced(
        np.arange(50), series, block_length=4, n_permutations=300, seed=11
    )
    assert first == second


# --- calibration: free shuffle is broken, the dependence-aware null is not ---


def _rates(trial) -> tuple[float, float]:
    free = aware = 0
    for t in range(TRIALS):
        f, a = trial(np.random.default_rng(10_000 + t), t)
        free += f < ALPHA
        aware += a < ALPHA
    return free / TRIALS, aware / TRIALS


@pytest.mark.slow
def test_a_random_walk_is_not_a_trend() -> None:
    def trial(rng: np.random.Generator, seed: int) -> tuple[float, float]:
        series = _random_walk(rng, 60)
        time = np.arange(60, dtype=float)
        free = permutation_test(time, series, kendall_tau_b, n_permutations=B, seed=seed)
        aware = trend_test_differenced(time, series, block_length=4, n_permutations=B, seed=seed)
        return free.p_value, aware.p_value

    free, aware = _rates(trial)
    assert free > BROKEN, f"free shuffle FPR {free:.3f}: expected the known failure"
    assert aware <= UPPER, f"differenced trend FPR {aware:.3f} exceeds {UPPER:.3f}"


@pytest.mark.slow
def test_two_unrelated_random_walks_are_not_correlated() -> None:
    def trial(rng: np.random.Generator, seed: int) -> tuple[float, float]:
        x, y = _random_walk(rng, 60), _random_walk(rng, 60)
        time = np.arange(60, dtype=float)
        free = permutation_test(x, y, spearman_rho, n_permutations=B, seed=seed)
        aware = correlation_test_differenced(
            time, x, y, block_length=4, n_permutations=B, seed=seed
        )
        return free.p_value, aware.p_value

    free, aware = _rates(trial)
    assert free > BROKEN, f"free shuffle FPR {free:.3f}: expected the known failure"
    assert aware <= UPPER, f"differenced correlation FPR {aware:.3f} exceeds {UPPER:.3f}"


@pytest.mark.slow
def test_a_shared_time_trend_is_not_a_correlation_in_a_panel() -> None:
    periods, entities = 20, 8
    strata = np.repeat(np.arange(periods), entities)

    def trial(rng: np.random.Generator, seed: int) -> tuple[float, float]:
        common = strata.astype(float)  # both columns rise with time, nothing else
        x = common + rng.normal(size=strata.size)
        y = common + rng.normal(size=strata.size)
        free = permutation_test(x, y, spearman_rho, n_permutations=B, seed=seed)
        aware = permutation_test_stratified(x, y, strata, spearman_rho, n_permutations=B, seed=seed)
        return free.p_value, aware.p_value

    free, aware = _rates(trial)
    assert free > BROKEN, f"free shuffle FPR {free:.3f}: expected the known failure"
    assert aware <= UPPER, f"stratified FPR {aware:.3f} exceeds {UPPER:.3f}"


@pytest.mark.slow
def test_entity_effects_are_not_a_group_difference() -> None:
    entities, rows = 12, 10
    clusters = np.repeat(np.arange(entities), rows)

    def trial(rng: np.random.Generator, seed: int) -> tuple[float, float]:
        entity_label = rng.permutation(np.array(["a"] * 6 + ["b"] * 6))
        labels = entity_label[clusters]
        values = 2.0 * rng.normal(size=entities)[clusters] + rng.normal(size=clusters.size)
        groups = [values[labels == "a"], values[labels == "b"]]
        free = permutation_test_groups(groups, _delta, n_permutations=B, seed=seed)
        aware = permutation_test_groups_clustered(
            values, labels, clusters, _delta, order=["a", "b"], n_permutations=B, seed=seed
        )
        return free.p_value, aware.p_value

    free, aware = _rates(trial)
    assert free > BROKEN, f"free shuffle FPR {free:.3f}: expected the known failure"
    assert aware <= UPPER, f"cluster FPR {aware:.3f} exceeds {UPPER:.3f}"
