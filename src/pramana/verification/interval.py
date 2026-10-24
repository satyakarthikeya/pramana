"""A dependence-aware bootstrap interval on the effect the gate gated on.

The resampling unit follows the permutation scheme, so rows that move together are never
treated as independent draws (an interval from resampled rows of a monthly table would be
far too narrow): whole entities for a cluster or paired null, whole periods for a
within-period null, rows for independent data. A block-differenced series has no
interval yet; it needs a block bootstrap of the changes, and no interval is better than a
narrow wrong one. Descriptive only: nothing here gates a verdict.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pramana.contracts import EffectInterval, PermutationScheme
from pramana.verification.attacks import ClaimView
from pramana.verification.schemes import PERIOD_COLUMN

#: Fewer successful resamples than this share of the request and the interval is not shown.
_MIN_VALID_SHARE = 0.8


def effect_interval(
    claim: ClaimView,
    rows: pd.DataFrame,
    *,
    n_resamples: int,
    confidence: float,
    seed: int,
) -> EffectInterval | None:
    """The percentile interval for `claim.effect` on `rows`, or None when not available.

    Guarantees: deterministic for a seed; the unit resampled follows `claim.scheme`;
    None for a block-differenced series, a missing unit column, or a statistic that
    cannot be computed on most resamples.
    """
    scheme = claim.scheme
    estimate = claim.effect(rows)
    if estimate is None:
        return None
    if scheme is PermutationScheme.BLOCK_DIFFERENCED:
        return None
    if scheme in (PermutationScheme.CLUSTER, PermutationScheme.PAIRED):
        column, method = claim.entity_column, "entity_bootstrap"
    elif scheme is PermutationScheme.STRATIFIED:
        column, method = PERIOD_COLUMN, "period_bootstrap"
    else:
        column, method = None, "row_bootstrap"
    if column is not None and column not in rows.columns:
        return None

    rng = np.random.default_rng(seed)
    if column is None:
        positions = np.arange(len(rows))
        groups = None
    else:
        keys = rows[column].astype(str).to_numpy()
        labels, inverse = np.unique(keys, return_inverse=True)
        groups = [np.flatnonzero(inverse == i) for i in range(len(labels))]
    effects: list[float] = []
    for _ in range(n_resamples):
        if groups is None:
            take = rng.choice(positions, size=positions.size, replace=True)
        else:
            chosen = rng.integers(0, len(groups), size=len(groups))
            take = np.concatenate([groups[i] for i in chosen])
        value = claim.effect(rows.iloc[take])
        if value is not None and np.isfinite(value):
            effects.append(float(value))
    if len(effects) < _MIN_VALID_SHARE * n_resamples:
        return None
    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(effects, [tail, 1.0 - tail])
    return EffectInterval(
        estimate=float(estimate),
        low=float(low),
        high=float(high),
        confidence=confidence,
        method=method,  # type: ignore[arg-type]
        n_resamples=len(effects),
    )
