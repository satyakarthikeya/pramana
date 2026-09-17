"""Effect-size estimators -- the "how big", reported next to every "how surprising".

A p-value answers one question ("could the null have produced this?") and says nothing
about whether the relationship matters. With n large enough, a rho of 0.02 clears any
alpha. AGENTS.md 3.5 therefore requires an effect alongside every p-value, and the gate
refuses a claim whose effect is negligible however small its q-value is.

Two families live here and they are not interchangeable:

  * **Gating metrics** -- `spearman_rho`, `kendall_tau_b`, `cliffs_delta`,
    `epsilon_squared`, `cramers_v`. Each is a member of `EffectMetric` and each has a
    band in `configs/verification.yaml`. They are scale-free, rank-based and bounded,
    which is what makes a fixed threshold meaningful across datasets.
  * **Reported metrics** -- `pearson_r`, `hedges_g`, `eta_squared`, `sens_slope`.
    Printed for human readers because "+0.4 visits per month" is actionable in a way
    that "tau = 0.31" is not. Nothing gates on them, so they need no threshold.

Rank-based by default, deliberately: the gate sees real survey data with heavy tails,
and one leverage point can manufacture a Pearson r of 0.9 out of noise.
`outlier_divergence` turns that failure mode into a signal by measuring exactly how
far the parametric and rank views disagree.

scipy is imported here and that is the point: this is the audited path
(`FORBIDDEN_SANDBOX_IMPORTS` in config.py blocks generated code from importing it
directly, while `pramana.verification.stats` stays on the whitelist). Everything in
this module is covered by known-answer tests and cross-checked against scipy where
scipy offers an independent implementation.

Every estimator refuses degenerate input rather than returning `nan`: a `nan` that
reaches the gate is a missing number wearing a float's clothes, and fail-closed means
raising where there is nothing to conclude.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 2
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy import stats

#: Below this, a correlation-style statistic has too few points to mean anything.
MIN_PAIRED_OBSERVATIONS = 3

#: Row ceiling for `sens_slope`, which materialises all n(n-1)/2 pairwise slopes.
#: At 3,000 rows that is ~4.5M pairs across roughly six intermediate arrays -- about
#: 216 MB, comfortably inside the executor's 1024 MB cap with room for the dataframe.
#: This is a MEMORY ceiling, not a statistical threshold, which is why it lives here
#: rather than in `configs/verification.yaml`: it is a property of the algorithm and
#: the sandbox, not a number anyone should tune to change what passes. Refusing loudly
#: above it beats being OOM-killed, which the gateway would have to read as an
#: execution failure and report as INCONCLUSIVE for entirely the wrong reason.
MAX_SENS_SLOPE_OBSERVATIONS = 3000


def _as_float_array(values: ArrayLike, *, name: str) -> NDArray[np.float64]:
    """`values` as a 1-D float array, with a message naming which argument was bad."""
    array = np.asarray(values, dtype=float).ravel()
    if array.size == 0:
        raise ValueError(f"{name} is empty; there is nothing to estimate")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains non-finite values; clean them before testing")
    return array


def _as_pair(
    x: ArrayLike, y: ArrayLike, *, min_n: int = MIN_PAIRED_OBSERVATIONS
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Two equal-length float arrays with at least `min_n` paired observations."""
    left = _as_float_array(x, name="x")
    right = _as_float_array(y, name="y")
    if left.size != right.size:
        raise ValueError(
            f"x and y must be of equal length; got {left.size} and {right.size}. "
            f"Rows were not paired, so nothing can be estimated from them."
        )
    if left.size < min_n:
        raise ValueError(
            f"{left.size} paired observations is below the minimum of {min_n}; "
            f"no association can be estimated from this many points"
        )
    return left, right


def _is_constant(values: NDArray[np.float64]) -> bool:
    """Whether every entry is identical -- i.e. the column carries no information."""
    return bool(values.size > 0 and np.all(values == values[0]))


# --- association ----------------------------------------------------------


def pearson_r(x: ArrayLike, y: ArrayLike) -> float:
    """Pearson product-moment correlation. REPORTED ONLY -- the gate never uses it.

    Guarantees: returns 0.0 for a constant column rather than `nan`. A column with no
    variance cannot covary with anything, so zero is the honest answer and `nan` would
    merely propagate.
    """
    left, right = _as_pair(x, y)
    if _is_constant(left) or _is_constant(right):
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])


def spearman_rho(x: ArrayLike, y: ArrayLike) -> float:
    """Spearman rank correlation -- the gating metric for `correlation` claims.

    Computed as Pearson's r on mid-ranks, which is the definition `scipy.stats
    .spearmanr` implements; the tests pin the two against each other.

    Guarantees: bounded in [-1, 1], 0.0 for a constant column, and invariant under any
    monotone transform of either column -- so a real but curved relationship is scored
    on its monotonicity rather than penalised for not being a straight line.
    """
    left, right = _as_pair(x, y)
    if _is_constant(left) or _is_constant(right):
        return 0.0
    return float(np.corrcoef(stats.rankdata(left), stats.rankdata(right))[0, 1])


def outlier_divergence(x: ArrayLike, y: ArrayLike) -> float:
    """How far the parametric and rank views of the same pair disagree.

    `|r - rho|`. A single leverage point can drag Pearson's r to 0.9 while rho stays
    near zero; a large divergence means the linear estimate is being carried by a
    handful of points. The gate reports it as `outlier_warning` rather than acting on
    it, because "this result is fragile" is information for a reader, not grounds to
    overturn a permutation test that already used ranks.
    """
    return abs(pearson_r(x, y) - spearman_rho(x, y))


# --- two-group difference -------------------------------------------------


def _two_groups(
    a: ArrayLike, b: ArrayLike, *, min_size: int
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    first = _as_float_array(a, name="group a")
    second = _as_float_array(b, name="group b")
    for name, group in (("group a", first), ("group b", second)):
        if group.size < min_size:
            raise ValueError(
                f"{name} has {group.size} observations; at least {min_size} are needed"
            )
    return first, second


def cliffs_delta(a: ArrayLike, b: ArrayLike) -> float:
    """Cliff's delta -- the gating metric for two-group `group_difference` claims.

    The probability that a random member of `a` exceeds a random member of `b`, minus
    the reverse: `delta = 2U / (n_a * n_b) - 1` for the Mann-Whitney U of `a`. Ties
    count as half, exactly as scipy's U does, and the tests pin the identity.

    Guarantees: bounded in [-1, 1], SIGNED (positive means `a` sits above `b`, which
    is why the gateway orders groups by the claim's `reference_group`), and
    distribution-free -- it reports dominance, not a difference in means, so a skewed
    income column does not need a log first.
    """
    first, second = _two_groups(a, b, min_size=1)
    ranks = stats.rankdata(np.concatenate([first, second]))
    u_statistic = float(ranks[: first.size].sum()) - first.size * (first.size + 1) / 2.0
    return 2.0 * u_statistic / (first.size * second.size) - 1.0


def hedges_g(a: ArrayLike, b: ArrayLike) -> float:
    """Hedges' g -- standardised mean difference. REPORTED ONLY.

    Cohen's d with the small-sample correction `J = 1 - 3 / (4(n_a + n_b) - 9)`
    applied. The correction only ever shrinks the estimate and costs nothing, so raw
    d is never the better choice.

    Guarantees: sign matches `cliffs_delta` (positive means `a` sits above `b`), and
    a zero pooled standard deviation raises rather than dividing by zero.
    """
    first, second = _two_groups(a, b, min_size=2)
    pooled_variance = (
        (first.size - 1) * np.var(first, ddof=1) + (second.size - 1) * np.var(second, ddof=1)
    ) / (first.size + second.size - 2)
    if pooled_variance <= 0.0:
        raise ValueError("pooled standard deviation is zero; a standardised difference is undefined")
    cohens_d = float((np.mean(first) - np.mean(second)) / np.sqrt(pooled_variance))
    correction = 1.0 - 3.0 / (4.0 * (first.size + second.size) - 9.0)
    return cohens_d * correction


# --- k-group --------------------------------------------------------------


def _k_groups(groups: Sequence[ArrayLike], *, min_groups: int = 2) -> list[NDArray[np.float64]]:
    if len(groups) < min_groups:
        raise ValueError(
            f"{len(groups)} group(s) given; at least {min_groups} are needed for a "
            f"between-group effect to exist at all"
        )
    parsed = [_as_float_array(group, name=f"group {index}") for index, group in enumerate(groups)]
    if any(group.size < 2 for group in parsed):
        raise ValueError("every group needs at least 2 observations")
    return parsed


def epsilon_squared(groups: Sequence[ArrayLike]) -> float:
    """Epsilon-squared -- the gating metric for k-group (k > 2) `group_difference`.

    The rank-based share of variation attributable to group membership,
    `eps^2 = H / (n - 1)` for the Kruskal-Wallis H.

    Guarantees: bounded in [0, 1] and UNSIGNED -- "these groups differ" has no
    direction to have, which is why the gateway reports no observed direction for it.
    Note that the gate thresholds its SQUARE ROOT, so it lands on the same scale as a
    correlation; a raw ratio of 0.02 looks negligible but is a rho-equivalent of 0.14.
    """
    parsed = _k_groups(groups)
    pooled = np.concatenate(parsed)
    if _is_constant(pooled):
        return 0.0
    h_statistic = float(stats.kruskal(*parsed).statistic)
    return max(0.0, min(1.0, h_statistic / (pooled.size - 1)))


def eta_squared(groups: Sequence[ArrayLike]) -> float:
    """Eta-squared -- the share of total sum of squares between groups. REPORTED ONLY.

    Guarantees: bounded in [0, 1]. Returns 0.0 when every observation is identical,
    where the ratio would otherwise be 0/0.
    """
    parsed = _k_groups(groups)
    pooled = np.concatenate(parsed)
    grand_mean = float(np.mean(pooled))
    ss_total = float(np.sum((pooled - grand_mean) ** 2))
    if ss_total <= 0.0:
        return 0.0
    ss_between = float(sum(group.size * (np.mean(group) - grand_mean) ** 2 for group in parsed))
    return max(0.0, min(1.0, ss_between / ss_total))


# --- trend ----------------------------------------------------------------


def kendall_tau_b(x: ArrayLike, y: ArrayLike) -> float:
    """Kendall's tau-b -- the gating metric for `trend` claims.

    The b variant, so ties are handled rather than ignored; pinned against
    `scipy.stats.kendalltau(variant="b")`.

    Why trend claims gate on tau instead of rho: a trend claim is about monotonicity,
    and tau is a direct probability of concordance. It runs systematically SMALLER
    than rho for the same relationship (`tau ~ (2/pi) arcsin(rho)`), which is exactly
    why `configs/verification.yaml` bands it separately -- a shared cutoff would make
    trend claims quietly harder to pass than correlation claims.
    """
    left, right = _as_pair(x, y)
    if _is_constant(left) or _is_constant(right):
        return 0.0
    return float(stats.kendalltau(left, right, variant="b").statistic)


def sens_slope(x: ArrayLike, y: ArrayLike) -> float:
    """Theil-Sen slope: the median of all pairwise slopes. REPORTED ONLY.

    This is the number a reader can act on -- "+0.4 visits per month" in the data's
    own units -- and the median makes it resistant to the outliers that would swing
    a least-squares fit. Up to ~29% of the points can be arbitrarily corrupted before
    the estimate breaks down.

    Guarantees: raises when no two x values differ, where every pairwise slope would
    be infinite, and refuses a dataset above `MAX_SENS_SLOPE_OBSERVATIONS` rather than
    exhausting the sandbox's memory on n(n-1)/2 pairs.
    """
    left, right = _as_pair(x, y)
    if left.size > MAX_SENS_SLOPE_OBSERVATIONS:
        raise ValueError(
            f"dataset too large for this estimator: {left.size} rows would materialise "
            f"{left.size * (left.size - 1) // 2} pairwise slopes, above the ceiling of "
            f"{MAX_SENS_SLOPE_OBSERVATIONS} rows. Subsample the frame or report a "
            f"different effect; this fails closed rather than exhausting the sandbox."
        )
    rows, columns = np.triu_indices(left.size, k=1)
    run = left[columns] - left[rows]
    usable = run != 0.0
    if not np.any(usable):
        raise ValueError("every x value is identical; no slope is defined")
    rise = right[columns] - right[rows]
    return float(np.median(rise[usable] / run[usable]))


# --- categorical ----------------------------------------------------------


def _contingency_table(table: ArrayLike) -> NDArray[np.float64]:
    counts = np.asarray(table, dtype=float)
    if counts.ndim != 2 or min(counts.shape) < 2:
        raise ValueError(
            f"a contingency table needs at least 2 rows and 2 columns; got shape {counts.shape}"
        )
    if np.any(counts < 0) or not np.all(np.isfinite(counts)):
        raise ValueError("contingency counts must be finite and non-negative")
    if counts.sum() <= 0:
        raise ValueError("contingency table is empty")
    return counts


def cramers_v(table: ArrayLike) -> float:
    """Cramer's V -- the gating metric for association between two categorical columns.

    `V = sqrt(chi2 / (n * (k - 1)))` with `k = min(rows, cols)`. No continuity
    correction: Yates' correction is built for hypothesis testing on 2x2 tables, and
    applying it here would bias the effect SIZE downward -- a perfect association
    would score 0.98 instead of 1.0.

    Guarantees: bounded in [0, 1], 0.0 for independence, 1.0 for a perfect
    association. Unsigned. Its gating band scales down with `table_k`, since a larger
    table can reach a given V with weaker per-cell association.
    """
    counts = _contingency_table(table)
    chi2 = float(stats.chi2_contingency(counts, correction=False).statistic)
    k = table_k(counts)
    return float(np.sqrt(chi2 / (counts.sum() * (k - 1))))


def table_k(table: ArrayLike) -> int:
    """`min(rows, cols)` -- the dimension Cramer's V is normalised by."""
    return int(min(_contingency_table(table).shape))
