"""Permutation tests whose null respects how the rows depend on each other (PLAN D6).

`permutation.py` shuffles rows freely, which is right only when rows are independent.
On a monthly series or a panel of regions, a free shuffle destroys the dependence that
chance alone would keep, so the null is too narrow and p-values come out too small: two
unrelated random walks look "significantly correlated" and a random walk looks like a
"significant trend". Each test here keeps that dependence inside the null instead.

  * `trend_test_differenced`        -- one ordered series. "Y tends to rise" is tested
    as "the first differences of Y do not average zero": the differences are sign-
    flipped in blocks and re-integrated, and Kendall's tau of the rebuilt series is the
    null. A drift survives; a random walk does not.
  * `correlation_test_differenced`  -- two ordered series. Changes against changes:
    Spearman's rho of the first differences, with the differences of y moved in blocks.
  * `permutation_test_stratified` / `permutation_test_groups_stratified` -- repeated
    periods. Values (or labels) move only within one period, so a common movement over
    time is part of the null rather than evidence.
  * `permutation_test_groups_clustered` -- repeated entities. A label moves between
    whole entities, never between rows of one entity.

Every result is stamped with its scheme (`PermutationScheme`), so the executor can
refuse a result built with a different null from the one the gate assigned.

Owner: P.P. Satya Karthikeya
Scope: PLAN_analysis_platform.md P1
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

from pramana.contracts.enums import PermutationScheme
from pramana.verification.stats.effect_size import (
    MINIMUM_COMPUTABLE_OBSERVATIONS,
    kendall_tau_b,
    spearman_rho,
)
from pramana.verification.stats.permutation import (
    Alternative,
    PermutationResult,
    _p_value,
    _stamped,
    _validate_run,
)


def default_block_length(n: int) -> int:
    """`ceil(n ** (1/3))`, the usual rate for block resampling, and at least 1."""
    return max(1, math.ceil(n ** (1.0 / 3.0)))


def lag1_autocorrelation(values: ArrayLike) -> float:
    """The lag-1 autocorrelation of a series; 0.0 for a constant or too-short one.

    Used by the gate as its screen on differenced series: differences that are still
    strongly autocorrelated mean differencing did not remove the dependence, and the
    claim is refused rather than tested.
    """
    series = np.asarray(values, dtype=float).ravel()
    if series.size < 3:
        return 0.0
    centred = series - series.mean()
    denominator = float(np.dot(centred, centred))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(centred[1:], centred[:-1]) / denominator)


def _ordered(time: ArrayLike, *columns: ArrayLike) -> list[NDArray[np.float64]]:
    """The columns sorted by time. Refuses repeated time points and short input."""
    order_by = np.asarray(time, dtype=float).ravel()
    parsed = [np.asarray(column, dtype=float).ravel() for column in columns]
    if any(column.size != order_by.size for column in parsed):
        raise ValueError("time and the series must be of equal length")
    if order_by.size < MINIMUM_COMPUTABLE_OBSERVATIONS + 1:
        raise ValueError(f"{order_by.size} points is too short a series to test")
    if np.unique(order_by).size != order_by.size:
        raise ValueError(
            "a time point repeats; a single series needs one value per time point "
            "(aggregate to one value per period first)"
        )
    order = np.argsort(order_by, kind="stable")
    return [column[order] for column in parsed]


def _check_block_length(block_length: int, n: int) -> None:
    if not 1 <= block_length <= n:
        raise ValueError(f"block_length must be between 1 and {n}; got {block_length}")


def _block_ids(n: int, block_length: int, rng: np.random.Generator) -> NDArray[np.int64]:
    """Block number of each position, with a random offset so block edges move."""
    offset = int(rng.integers(block_length))
    return (np.arange(n) + offset) // block_length


def _block_signs(n: int, block_length: int, rng: np.random.Generator) -> NDArray[np.float64]:
    ids = _block_ids(n, block_length, rng)
    signs = rng.choice(np.array([-1.0, 1.0]), size=int(ids[-1]) + 1)
    return signs[ids]


def _block_order(n: int, block_length: int, rng: np.random.Generator) -> NDArray[np.int64]:
    """A permutation of positions that keeps runs of `block_length` together."""
    ids = _block_ids(n, block_length, rng)
    blocks = [np.flatnonzero(ids == b) for b in range(int(ids[-1]) + 1)]
    return np.concatenate([blocks[i] for i in rng.permutation(len(blocks))])


def trend_test_differenced(
    time: ArrayLike,
    values: ArrayLike,
    *,
    block_length: int,
    n_permutations: int,
    seed: int,
    alternative: Alternative = "two-sided",
) -> PermutationResult:
    """Test a trend in one ordered series without mistaking a random walk for one.

    The statistic is Kendall's tau-b of the series against its order. The null keeps
    the size and the short-range dependence of every step but not its sign: the first
    differences are sign-flipped in blocks of `block_length` and re-integrated from the
    first value. A series that only wanders has steps that average zero, so flipping
    them changes nothing systematic; a series that drifts loses its drift.

    Guarantees: deterministic for a given seed; the observed statistic does not depend
    on the seed; p is never below `1 / (n_permutations + 1)`; the result is stamped
    `BLOCK_DIFFERENCED`. Raises on repeated time points.
    """
    _validate_run(n_permutations, alternative)
    (series,) = _ordered(time, values)
    _check_block_length(block_length, series.size - 1)
    index = np.arange(series.size, dtype=float)
    observed = float(kendall_tau_b(index, series))
    steps = np.diff(series)
    rng = np.random.default_rng(seed)
    null_distribution = np.empty(n_permutations, dtype=float)
    rebuilt = np.empty_like(series)
    rebuilt[0] = series[0]
    for i in range(n_permutations):
        flipped = steps * _block_signs(steps.size, block_length, rng)
        rebuilt[1:] = series[0] + np.cumsum(flipped)
        null_distribution[i] = float(kendall_tau_b(index, rebuilt))
    return _stamped(
        _p_value(observed, null_distribution, alternative),
        observed,
        n_permutations,
        seed,
        PermutationScheme.BLOCK_DIFFERENCED,
    )


def correlation_test_differenced(
    time: ArrayLike,
    x: ArrayLike,
    y: ArrayLike,
    *,
    block_length: int,
    n_permutations: int,
    seed: int,
    alternative: Alternative = "two-sided",
) -> PermutationResult:
    """Test whether two ordered series move together, change for change.

    Both series are first-differenced; the statistic is Spearman's rho of the changes.
    The null moves the changes of `y` in blocks of `block_length`, which keeps their
    short-range dependence and breaks only their alignment with `x`.

    Guarantees: as `trend_test_differenced`. The effect is about CHANGES, and the
    claim's wording must say so.
    """
    _validate_run(n_permutations, alternative)
    left, right = _ordered(time, x, y)
    dx, dy = np.diff(left), np.diff(right)
    _check_block_length(block_length, dy.size)
    observed = float(spearman_rho(dx, dy))
    rng = np.random.default_rng(seed)
    null_distribution = np.empty(n_permutations, dtype=float)
    for i in range(n_permutations):
        null_distribution[i] = float(spearman_rho(dx, dy[_block_order(dy.size, block_length, rng)]))
    return _stamped(
        _p_value(observed, null_distribution, alternative),
        observed,
        n_permutations,
        seed,
        PermutationScheme.BLOCK_DIFFERENCED,
    )


def _strata_codes(strata: ArrayLike, n: int) -> NDArray[np.int64]:
    labels = np.asarray(strata, dtype=object).ravel()
    if labels.size != n:
        raise ValueError(f"strata must have one entry per row; got {labels.size} for {n} rows")
    _, codes = np.unique(labels.astype(str), return_inverse=True)
    return codes.astype(np.int64)


def _within_strata(codes: NDArray[np.int64], rng: np.random.Generator) -> NDArray[np.int64]:
    """A permutation of positions that never moves a row out of its stratum."""
    return np.lexsort((rng.random(codes.size), codes))


def _movable_rows(codes: NDArray[np.int64]) -> int:
    counts = np.bincount(codes)
    return int(counts[counts >= 2].sum())


def permutation_test_stratified(
    x: ArrayLike,
    y: ArrayLike,
    strata: ArrayLike,
    statistic: Callable[[NDArray[np.float64], NDArray[np.float64]], float],
    *,
    n_permutations: int,
    seed: int,
    alternative: Alternative = "two-sided",
) -> PermutationResult:
    """Test a paired relationship by shuffling `y` only within each stratum (period).

    Within a period the rows are exchangeable under the null; across periods they are
    not, because everything can move with time. Keeping each value in its own period
    puts that common movement into the null, so it is not counted as evidence.

    Guarantees: as `permutation_test`, plus no value ever leaves its stratum; the result
    is stamped `STRATIFIED`. Refuses strata that leave too few rows free to move.
    """
    _validate_run(n_permutations, alternative)
    left = np.asarray(x, dtype=float).ravel()
    right = np.asarray(y, dtype=float).ravel()
    if left.size != right.size:
        raise ValueError(f"x and y must be of equal length; got {left.size} and {right.size}")
    codes = _strata_codes(strata, left.size)
    if _movable_rows(codes) < MINIMUM_COMPUTABLE_OBSERVATIONS:
        raise ValueError("too few rows share a stratum with another row; nothing can move")
    observed = float(statistic(left, right))
    rng = np.random.default_rng(seed)
    null_distribution = np.empty(n_permutations, dtype=float)
    # positions sorted by stratum; a draw re-orders rows inside each stratum only
    home = np.argsort(codes, kind="stable")
    for i in range(n_permutations):
        shuffled = np.empty_like(right)
        shuffled[home] = right[_within_strata(codes, rng)]
        null_distribution[i] = float(statistic(left, shuffled))
    return _stamped(
        _p_value(observed, null_distribution, alternative),
        observed,
        n_permutations,
        seed,
        PermutationScheme.STRATIFIED,
    )


def _groups(
    values: NDArray[np.float64], labels: NDArray[np.str_], order: Sequence[str]
) -> list[NDArray[np.float64]]:
    return [values[labels == name] for name in order]


def _parse_groups(
    values: ArrayLike, labels: ArrayLike, order: Sequence[str]
) -> tuple[NDArray[np.float64], NDArray[np.str_]]:
    parsed = np.asarray(values, dtype=float).ravel()
    names = np.asarray(labels, dtype=object).ravel().astype(str)
    if parsed.size != names.size:
        raise ValueError("values and labels must be of equal length")
    if len(order) < 2 or len(set(order)) != len(order):
        raise ValueError("order must name at least 2 distinct groups")
    if set(names) != set(order):
        raise ValueError("order must name every label exactly once")
    if parsed.size < MINIMUM_COMPUTABLE_OBSERVATIONS:
        raise ValueError(f"{parsed.size} observations is too few to compare groups")
    return parsed, names


def permutation_test_groups_stratified(
    values: ArrayLike,
    labels: ArrayLike,
    strata: ArrayLike,
    statistic: Callable[[list[NDArray[np.float64]]], float],
    *,
    order: Sequence[str],
    n_permutations: int,
    seed: int,
    alternative: Alternative = "two-sided",
) -> PermutationResult:
    """Test a group difference by reshuffling labels only within each stratum (period).

    Every period keeps its own mix of labels, so a group that happens to be common in a
    high period gains nothing from that in the null either.

    Guarantees: as `permutation_test_groups`, with `statistic` receiving the groups in
    `order`; every stratum keeps its label counts in every resample; stamped
    `STRATIFIED`. Refuses when no stratum holds two different labels.
    """
    _validate_run(n_permutations, alternative)
    parsed, names = _parse_groups(values, labels, order)
    codes = _strata_codes(strata, parsed.size)
    mixed = sum(np.unique(names[codes == c]).size >= 2 for c in np.unique(codes))
    if mixed == 0:
        raise ValueError("no stratum holds two different labels; nothing can move")
    observed = float(statistic(_groups(parsed, names, order)))
    rng = np.random.default_rng(seed)
    home = np.argsort(codes, kind="stable")
    null_distribution = np.empty(n_permutations, dtype=float)
    for i in range(n_permutations):
        shuffled = np.empty_like(names)
        shuffled[home] = names[_within_strata(codes, rng)]
        null_distribution[i] = float(statistic(_groups(parsed, shuffled, order)))
    return _stamped(
        _p_value(observed, null_distribution, alternative),
        observed,
        n_permutations,
        seed,
        PermutationScheme.STRATIFIED,
    )


def permutation_test_groups_clustered(
    values: ArrayLike,
    labels: ArrayLike,
    clusters: ArrayLike,
    statistic: Callable[[list[NDArray[np.float64]]], float],
    *,
    order: Sequence[str],
    n_permutations: int,
    seed: int,
    alternative: Alternative = "two-sided",
) -> PermutationResult:
    """Test a group difference by moving labels between whole entities (clusters).

    Rows of one entity are alike for reasons that have nothing to do with the label, so
    shuffling rows would treat one entity's many rows as many independent witnesses.
    Here each entity keeps all its rows and only the entity's label moves.

    Guarantees: as `permutation_test_groups`; each label keeps its number of entities in
    every resample; stamped `CLUSTER`. Refuses a label that varies within an entity.
    """
    _validate_run(n_permutations, alternative)
    parsed, names = _parse_groups(values, labels, order)
    codes = _strata_codes(clusters, parsed.size)
    n_clusters = int(codes.max()) + 1
    cluster_label = np.empty(n_clusters, dtype=names.dtype)
    for c in range(n_clusters):
        own = np.unique(names[codes == c])
        if own.size != 1:
            raise ValueError(
                "a label varies within one entity, so labels cannot be moved between whole entities"
            )
        cluster_label[c] = own[0]
    if np.unique(cluster_label).size < 2:
        raise ValueError("every entity has the same label; there is nothing to compare")
    observed = float(statistic(_groups(parsed, names, order)))
    rng = np.random.default_rng(seed)
    null_distribution = np.empty(n_permutations, dtype=float)
    for i in range(n_permutations):
        moved = rng.permutation(cluster_label)[codes]
        null_distribution[i] = float(statistic(_groups(parsed, moved, order)))
    return _stamped(
        _p_value(observed, null_distribution, alternative),
        observed,
        n_permutations,
        seed,
        PermutationScheme.CLUSTER,
    )
