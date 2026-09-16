"""Bootstrap confidence intervals -- how precise the effect is, not whether it exists.

The permutation test answers "could chance have done this?". The bootstrap answers a
different question the report also needs: "if we ran this study again, how much would
the effect move?". A rho of 0.4 with a CI of [0.38, 0.42] and a rho of 0.4 with a CI
of [0.02, 0.71] are not the same finding, and only one of them should be repeated to
a reader without qualification.

The interval is the percentile bootstrap: resample rows with replacement, recompute
the statistic, and read the empirical quantiles. It assumes nothing about the shape of
the sampling distribution, which is the same reason the gate permutes rather than
consulting a t-table.

Paired resampling is not optional
---------------------------------
For an association, resampling each column independently would destroy the very thing
being estimated -- the CI would collapse toward zero and every real finding would look
fragile. `paired=True` resamples ROW INDICES and applies them to every column at once,
so a resample is a plausible alternative dataset rather than a reshuffle.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 2
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray
from pydantic import BaseModel, ConfigDict, Field

from pramana.verification.stats import provenance

#: Below this there is nothing to resample from.
MIN_OBSERVATIONS = 3


class BootstrapResult(BaseModel):
    """One executed bootstrap.

    Guarantees: `ci_low <= point_estimate <= ci_high` is NOT asserted -- a skewed
    statistic can put its point estimate outside a percentile interval, and hiding
    that would be a lie about the method. `excludes_zero` is derived, never set.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    point_estimate: float = Field(description="The statistic on the real sample, computed once.")
    ci_low: float
    ci_high: float
    confidence_level: float = Field(gt=0.0, lt=1.0)
    n_bootstrap: int = Field(ge=1)
    seed: int
    provenance: str | None = Field(
        default=None,
        description="HMAC stamp proving this came from here. Null outside the sandbox.",
    )

    @property
    def excludes_zero(self) -> bool:
        """Whether the interval sits entirely on one side of zero.

        Reported alongside the permutation p-value, never in place of it: an interval
        that excludes zero is corroboration, and the verdict still comes from the
        BH-corrected q-value.
        """
        return self.ci_low > 0.0 or self.ci_high < 0.0


def _validate(n_bootstrap: int, confidence_level: float) -> None:
    if n_bootstrap < 1:
        raise ValueError(f"n_bootstrap must be at least 1; got {n_bootstrap}")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError(
            f"confidence_level must be strictly between 0 and 1; got {confidence_level}"
        )


def _columns(data: ArrayLike | Sequence[ArrayLike], *, paired: bool) -> list[NDArray[np.float64]]:
    """The data as one column, or as several equal-length paired columns."""
    if not paired:
        return [np.asarray(data, dtype=float).ravel()]
    parsed = [np.asarray(column, dtype=float).ravel() for column in data]  # type: ignore[union-attr]
    if len(parsed) < 2:
        raise ValueError("paired resampling needs at least 2 columns")
    sizes = {column.size for column in parsed}
    if len(sizes) != 1:
        raise ValueError(
            f"paired columns must be of equal length; got sizes {sorted(sizes)}. "
            f"Rows that are not aligned cannot be resampled together."
        )
    return parsed


def bootstrap_ci(
    data: ArrayLike | Sequence[ArrayLike],
    statistic: Callable[..., Any],
    *,
    n_bootstrap: int,
    seed: int,
    confidence_level: float = 0.95,
    paired: bool = False,
) -> BootstrapResult:
    """Percentile bootstrap interval for `statistic` on `data`.

    With `paired=False`, `data` is one column and `statistic` is called with it.
    With `paired=True`, `data` is a sequence of equal-length columns and `statistic`
    is called with all of them, resampled by a shared set of row indices.

    Guarantees: the same `(data, statistic, n_bootstrap, seed, confidence_level)`
    always produces the same interval; the interval narrows as the sample grows and
    widens as the confidence level rises; invalid parameters and too-short input raise
    rather than returning an interval nobody should trust.
    """
    _validate(n_bootstrap, confidence_level)
    columns = _columns(data, paired=paired)
    n_rows = columns[0].size
    if n_rows < MIN_OBSERVATIONS:
        raise ValueError(
            f"{n_rows} observations is below the minimum of at least {MIN_OBSERVATIONS}; "
            f"a bootstrap interval from this many points is not meaningful"
        )

    point_estimate = float(statistic(*columns))
    rng = np.random.default_rng(seed)
    replicates = np.empty(n_bootstrap, dtype=float)
    for index in range(n_bootstrap):
        rows = rng.integers(0, n_rows, size=n_rows)
        replicates[index] = float(statistic(*(column[rows] for column in columns)))

    tail = (1.0 - confidence_level) / 2.0
    low, high = (float(bound) for bound in np.quantile(replicates, [tail, 1.0 - tail]))
    return BootstrapResult(
        point_estimate=point_estimate,
        ci_low=low,
        ci_high=high,
        confidence_level=confidence_level,
        n_bootstrap=n_bootstrap,
        seed=seed,
        provenance=provenance.stamp((point_estimate, low, high, n_bootstrap, seed)),
    )
