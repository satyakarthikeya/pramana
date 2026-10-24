"""Tests for the two time claims added in P7: period change (T4) and seasonality (T6).

  * `period_change_test_paired`  -- the same entities in two periods (a panel). The
    change of each entity is sign-flipped: under the null an entity was as likely to
    fall as to rise by the amount it moved.
  * `period_change_test_groups`  -- rows of two periods (a ledger). Rows are moved
    between the two periods with the period sizes kept.
  * `seasonality_test`           -- a month-of-year (or quarter) effect. Each year is
    centred on its own mean, so a trend across years is not a season; the cycle labels
    are then shuffled only within each year.

The statistic of both change tests is the relative change of the mean,
`(mean(current) - mean(previous)) / |mean(previous)|`, and the result is refused when
the previous mean is zero, because a relative change from zero is undefined.

Owner: P.P. Satya Karthikeya
Scope: PLAN_analysis_platform.md P7 (T4, T6)
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from pramana.contracts.enums import PermutationScheme
from pramana.verification.stats.effect_size import epsilon_squared
from pramana.verification.stats.permutation import (
    Alternative,
    PermutationResult,
    _p_value,
    _stamped,
    _validate_run,
)


def relative_change(previous: ArrayLike, current: ArrayLike) -> float:
    """`(mean(current) - mean(previous)) / |mean(previous)|`. Raises for a zero base."""
    before = float(np.mean(np.asarray(previous, dtype=float)))
    after = float(np.mean(np.asarray(current, dtype=float)))
    if before == 0.0:
        raise ValueError("the previous period's mean is zero; a relative change is undefined")
    return (after - before) / abs(before)


def period_change_test_paired(
    previous: ArrayLike,
    current: ArrayLike,
    *,
    n_permutations: int,
    seed: int,
    alternative: Alternative = "two-sided",
) -> PermutationResult:
    """Test a change between two periods measured on the same entities.

    Guarantees: entity i's two values stay together; only the sign of its change is
    flipped. Stamped `PAIRED`. Refuses fewer than 4 entities or a zero previous mean.
    """
    _validate_run(n_permutations, alternative)
    before = np.asarray(previous, dtype=float).ravel()
    after = np.asarray(current, dtype=float).ravel()
    if before.size != after.size:
        raise ValueError("each entity needs a value in both periods")
    if before.size < 4:
        raise ValueError(f"{before.size} entities is too few to test a change")
    base = abs(float(before.mean()))
    if base == 0.0:
        raise ValueError("the previous period's mean is zero; a relative change is undefined")
    steps = after - before
    observed = float(steps.mean() / base)
    rng = np.random.default_rng(seed)
    signs = rng.choice(np.array([-1.0, 1.0]), size=(n_permutations, steps.size))
    null_distribution = (signs * steps).mean(axis=1) / base
    return _stamped(
        _p_value(observed, null_distribution, alternative),
        observed,
        n_permutations,
        seed,
        PermutationScheme.PAIRED,
    )


def period_change_test_groups(
    previous: ArrayLike,
    current: ArrayLike,
    *,
    n_permutations: int,
    seed: int,
    alternative: Alternative = "two-sided",
) -> PermutationResult:
    """Test a change between the rows of two periods (no entity is followed).

    Guarantees: rows move between the two periods with each period's size kept.
    Stamped `FREE`. Refuses a period with fewer than 2 rows or a zero previous mean.
    """
    _validate_run(n_permutations, alternative)
    before = np.asarray(previous, dtype=float).ravel()
    after = np.asarray(current, dtype=float).ravel()
    if before.size < 2 or after.size < 2:
        raise ValueError("each period needs at least 2 rows")
    observed = relative_change(before, after)
    pooled = np.concatenate([before, after])
    rng = np.random.default_rng(seed)
    null_distribution = np.empty(n_permutations, dtype=float)
    for i in range(n_permutations):
        rng.shuffle(pooled)
        base = abs(float(pooled[: before.size].mean()))
        null_distribution[i] = (
            (float(pooled[before.size :].mean()) - float(pooled[: before.size].mean())) / base
            if base > 0
            else 0.0
        )
    return _stamped(
        _p_value(observed, null_distribution, alternative),
        observed,
        n_permutations,
        seed,
        PermutationScheme.FREE,
    )


def _centred_groups(
    values: NDArray[np.float64], cycles: NDArray[np.int64], years: NDArray[np.int64]
) -> list[NDArray[np.float64]]:
    centred = values.copy()
    for year in np.unique(years):
        mask = years == year
        centred[mask] -= centred[mask].mean()
    return [centred[cycles == c] for c in np.unique(cycles)]


def seasonality_test(
    values: ArrayLike,
    cycle: ArrayLike,
    year: ArrayLike,
    *,
    n_permutations: int,
    seed: int,
    alternative: Alternative = "two-sided",
) -> PermutationResult:
    """Test whether some months (or quarters) sit consistently above others.

    Each year is centred on its own mean, then epsilon-squared across cycle positions
    is the statistic. The null shuffles cycle labels within each year, so a year that
    was simply higher overall carries no seasonal information.

    Guarantees: stamped `STRATIFIED`; deterministic for a seed; refuses fewer than two
    years or a cycle position seen only once. The statistic is never negative, so
    "two-sided" and "greater" are the same test; "less" is refused.
    """
    _validate_run(n_permutations, alternative)
    if alternative == "less":
        raise ValueError("a seasonal effect has no direction; 'less' is not a valid test")
    series = np.asarray(values, dtype=float).ravel()
    cycles = np.asarray(cycle, dtype=np.int64).ravel()
    years = np.asarray(year, dtype=np.int64).ravel()
    if not series.size == cycles.size == years.size:
        raise ValueError("values, cycle and year must be of equal length")
    if np.unique(years).size < 2:
        raise ValueError("a seasonal pattern needs at least two years")
    counts = np.bincount(cycles - cycles.min())
    if (counts[counts > 0] < 2).any():
        raise ValueError("every month (or quarter) needs at least two years of values")
    observed = float(epsilon_squared(_centred_groups(series, cycles, years)))
    rng = np.random.default_rng(seed)
    order = [np.flatnonzero(years == y) for y in np.unique(years)]
    null_distribution = np.empty(n_permutations, dtype=float)
    shuffled = cycles.copy()
    for i in range(n_permutations):
        for positions in order:
            shuffled[positions] = cycles[rng.permutation(positions)]
        null_distribution[i] = float(epsilon_squared(_centred_groups(series, shuffled, years)))
    return _stamped(
        _p_value(observed, null_distribution, "greater"),
        observed,
        n_permutations,
        seed,
        PermutationScheme.STRATIFIED,
    )


# --- row-level entry points: the selection happens here, in audited code ---------
#
# Generated code may not filter rows (`executor/policy.py`), so it cannot pick "the last
# two periods" itself. These take every row and do the selection in trusted code.


def _last_two(periods: NDArray[np.float64]) -> tuple[float, float]:
    distinct = np.unique(periods[~np.isnan(periods)])
    if distinct.size < 2:
        raise ValueError("a change needs at least two periods")
    return float(distinct[-2]), float(distinct[-1])


def latest_change_test(
    values: ArrayLike,
    periods: ArrayLike,
    entities: ArrayLike | None = None,
    *,
    n_permutations: int,
    seed: int,
    alternative: Alternative = "two-sided",
) -> PermutationResult:
    """Test the change from the second-latest to the latest period.

    With `entities`, each entity's mean in the two periods is paired (entities present
    in only one are left out) and `period_change_test_paired` runs; without, the rows of
    the two periods are compared with `period_change_test_groups`.
    """
    series = np.asarray(values, dtype=float).ravel()
    keys = np.asarray(periods, dtype=float).ravel()
    previous, current = _last_two(keys)
    if entities is None:
        return period_change_test_groups(
            series[keys == previous],
            series[keys == current],
            n_permutations=n_permutations,
            seed=seed,
            alternative=alternative,
        )
    names = np.asarray(entities, dtype=object).ravel().astype(str)
    before, after = [], []
    for name in np.unique(names):
        mine = names == name
        a, b = series[mine & (keys == previous)], series[mine & (keys == current)]
        if a.size and b.size:
            before.append(a.mean())
            after.append(b.mean())
    return period_change_test_paired(
        before, after, n_permutations=n_permutations, seed=seed, alternative=alternative
    )


def latest_absolute_change(values: ArrayLike, periods: ArrayLike) -> float:
    """Mean of the latest period minus mean of the one before, in the column's units."""
    series = np.asarray(values, dtype=float).ravel()
    keys = np.asarray(periods, dtype=float).ravel()
    previous, current = _last_two(keys)
    return float(series[keys == current].mean() - series[keys == previous].mean())


def _cycle_frame(
    values: ArrayLike, periods: ArrayLike, cycle_length: int
) -> tuple[NDArray[np.float64], NDArray[np.int64], NDArray[np.int64]]:
    """Per-period means with their cycle position and year (period ordinals)."""
    series = np.asarray(values, dtype=float).ravel()
    keys = np.asarray(periods, dtype=float).ravel()
    distinct = np.unique(keys[~np.isnan(keys)])
    means = np.array([series[keys == k].mean() for k in distinct])
    ordinals = np.round(distinct).astype(np.int64)
    return means, ordinals % cycle_length, ordinals // cycle_length


def seasonality_test_from_periods(
    values: ArrayLike,
    periods: ArrayLike,
    *,
    cycle_length: int,
    n_permutations: int,
    seed: int,
    alternative: Alternative = "two-sided",
) -> PermutationResult:
    """`seasonality_test` on the per-period means of `values`.

    `periods` are period ordinals (months since 1970-01 for monthly data, quarters for
    quarterly), so `ordinal % cycle_length` is the month or quarter of the year.
    """
    means, cycles, years = _cycle_frame(values, periods, cycle_length)
    return seasonality_test(
        means, cycles, years, n_permutations=n_permutations, seed=seed, alternative=alternative
    )


def seasonal_range(values: ArrayLike, periods: ArrayLike, *, cycle_length: int) -> float:
    """Peak minus trough of the average year, after centring each year: REPORTED ONLY."""
    means, cycles, years = _cycle_frame(values, periods, cycle_length)
    groups = _centred_groups(means, cycles, years)
    profile = [float(g.mean()) for g in groups]
    return max(profile) - min(profile)
