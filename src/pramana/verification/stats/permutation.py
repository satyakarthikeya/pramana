"""Permutation testing -- the trust anchor of the whole gateway.

Every PASS the gateway issues traces back to a p-value produced here. Not by an LLM
reasoning about significance, and not by a parametric formula whose assumptions nobody
checked -- by actually destroying the claimed relationship thousands of times and
counting how often chance did as well as the real data (AGENTS.md 3.1).

Why permutation rather than a t-test or scipy's analytic p-values
-----------------------------------------------------------------
The null is constructed from the data itself by shuffling, so it inherits the data's
actual marginal distributions. No normality assumption, no equal-variance assumption,
nothing to be wrong about on a skewed income column or a Likert scale. The cost is
compute, which is the cheapest thing we have.

The add-one rule
----------------
`p = (1 + #{as extreme as observed}) / (B + 1)`, never `#/B`. Two reasons, and both
matter for the report:

  * A test with B resamples cannot resolve finer than `1 / (B + 1)`. Reporting
    `p = 0` would claim infinite precision from finite compute, and the executor
    treats an exact zero as proof that a number did not come from this function.
  * The observed statistic is itself one draw from the null under H0, so counting it
    keeps the test exact -- the false-positive rate is at most alpha rather than
    approximately alpha. `test_null_calibration_false_positive_rate` is what pins
    this, and it is the test that licenses the FDR claim downstream.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 2
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field

from pramana.verification.stats import provenance

#: How the observed statistic is compared against the null distribution.
Alternative = Literal["two-sided", "greater", "less"]

#: Below this there is no relationship to shuffle.
MIN_OBSERVATIONS = 3

#: Guards the "as extreme as" comparison against floating-point noise: a permutation
#: that reproduces the observed statistic up to rounding COUNTS. Erring this way makes
#: the p-value larger, which is the fail-closed direction.
_TOLERANCE = 1e-12


class PermutationResult(BaseModel):
    """One executed permutation test.

    Guarantees: `p_value` is in `[p_value_floor, 1.0]` and never zero; `statistic` is
    the observed value and does not depend on `seed`; `seed` and `n_permutations` are
    carried so the run can be reproduced exactly (AGENTS.md 3.4).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    p_value: float = Field(gt=0.0, le=1.0)
    statistic: float = Field(description="The observed statistic, computed once on the real data.")
    n_permutations: int = Field(ge=1)
    seed: int
    provenance: str | None = Field(
        default=None,
        description="HMAC stamp proving this came from here. Null outside the sandbox.",
    )

    @property
    def p_value_floor(self) -> float:
        """`1 / (B + 1)` -- the smallest p-value this many resamples can resolve."""
        return 1.0 / (self.n_permutations + 1)


def _validate_run(n_permutations: int, alternative: str) -> None:
    if n_permutations < 1:
        raise ValueError(f"n_permutations must be at least 1; got {n_permutations}")
    if alternative not in ("two-sided", "greater", "less"):
        raise ValueError(
            f"alternative must be 'two-sided', 'greater' or 'less'; got {alternative!r}"
        )


def _p_value(
    observed: float, null_distribution: NDArray[np.float64], alternative: Alternative
) -> float:
    """The add-one p-value: how often chance alone did as well as the real data."""
    if alternative == "greater":
        as_extreme = null_distribution >= observed - _TOLERANCE
    elif alternative == "less":
        as_extreme = null_distribution <= observed + _TOLERANCE
    else:
        as_extreme = np.abs(null_distribution) >= abs(observed) - _TOLERANCE
    return float((1 + int(np.count_nonzero(as_extreme))) / (null_distribution.size + 1))


def _stamped(
    p_value: float, statistic: float, n_permutations: int, seed: int
) -> PermutationResult:
    """Build the result and stamp it, so a caller can tell it came from this function.

    The stamped fields are exactly the numbers the executor reads back out of the
    generated code's payload, so a value altered anywhere in between fails the check
    (see `stats/provenance.py`).
    """
    return PermutationResult(
        p_value=p_value,
        statistic=statistic,
        n_permutations=n_permutations,
        seed=seed,
        provenance=provenance.stamp((p_value, statistic, n_permutations, seed)),
    )


def permutation_test(
    x: ArrayLike,
    y: ArrayLike,
    statistic: Callable[[NDArray[np.float64], NDArray[np.float64]], float],
    *,
    n_permutations: int,
    seed: int,
    alternative: Alternative = "two-sided",
) -> PermutationResult:
    """Test a paired relationship by shuffling one column against the other.

    Shuffling `y` breaks any association while leaving both marginal distributions
    exactly as they were -- that IS the null hypothesis, realised rather than assumed.

    Guarantees: the same `(x, y, statistic, n_permutations, seed)` always produces the
    same p-value; `statistic` is evaluated once on the real data and that observed
    value does not depend on `seed`; the returned p-value is never zero and never
    below `1 / (n_permutations + 1)`. Raises on mismatched or too-short input rather
    than testing something meaningless.
    """
    _validate_run(n_permutations, alternative)
    left = np.asarray(x, dtype=float).ravel()
    right = np.asarray(y, dtype=float).ravel()
    if left.size != right.size:
        raise ValueError(
            f"x and y must be of equal length; got {left.size} and {right.size}. "
            f"Unpaired rows cannot be tested."
        )
    if left.size < MIN_OBSERVATIONS:
        raise ValueError(
            f"{left.size} paired observations is below the minimum of {MIN_OBSERVATIONS}; "
            f"a permutation test on this many points concludes nothing"
        )

    observed = float(statistic(left, right))
    rng = np.random.default_rng(seed)
    shuffled = right.copy()
    null_distribution = np.empty(n_permutations, dtype=float)
    for index in range(n_permutations):
        rng.shuffle(shuffled)
        null_distribution[index] = float(statistic(left, shuffled))

    return _stamped(
        _p_value(observed, null_distribution, alternative), observed, n_permutations, seed
    )


def permutation_test_groups(
    groups: Sequence[ArrayLike],
    statistic: Callable[[list[NDArray[np.float64]]], float],
    *,
    n_permutations: int,
    seed: int,
    alternative: Alternative = "two-sided",
) -> PermutationResult:
    """Test a group difference by reshuffling which group each observation belongs to.

    Group SIZES are preserved and only the labels move, so the null is precisely
    "which group you are in tells you nothing about the value" -- and any imbalance in
    the design survives into the null rather than being assumed away.

    Guarantees: as `permutation_test`, plus every group keeps its original size in
    every resample.
    """
    _validate_run(n_permutations, alternative)
    parsed = [np.asarray(group, dtype=float).ravel() for group in groups]
    if len(parsed) < 2:
        raise ValueError(f"{len(parsed)} group(s) given; at least 2 are needed to compare")
    if any(group.size < 2 for group in parsed):
        raise ValueError("every group needs at least 2 observations")
    total = sum(group.size for group in parsed)
    if total < MIN_OBSERVATIONS:
        raise ValueError(
            f"{total} observations across all groups is below the minimum of "
            f"{MIN_OBSERVATIONS}; nothing can be concluded"
        )

    observed = float(statistic(parsed))
    pooled = np.concatenate(parsed)
    split_points = np.cumsum([group.size for group in parsed])[:-1]
    rng = np.random.default_rng(seed)
    null_distribution = np.empty(n_permutations, dtype=float)
    for index in range(n_permutations):
        rng.shuffle(pooled)
        null_distribution[index] = float(statistic(list(np.split(pooled, split_points))))

    return _stamped(
        _p_value(observed, null_distribution, alternative), observed, n_permutations, seed
    )
