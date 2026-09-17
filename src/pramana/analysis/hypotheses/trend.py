"""Datetime x numeric -> trend candidates.

Kendall's tau-b for the pre-filter, because that is what the gateway gates trend
claims on (`falsification/templates.py`). Tau runs systematically smaller than
Spearman's rho for the same relationship, so filtering on rho and testing on tau would
propose pairs that cannot clear the band they are measured against.

What counts as a time axis is decided by schema inference, not here: a `DATETIME`
column, or an `ORDINAL` column whose name marks it as one (`is_time_like`). A frame
with no such column yields no trend candidates, which is correct -- "rises over time"
needs a time.

Owner: P. Rohith (built by P.P. Satya Karthikeya -- team-agreed cross-module work)
Scope: scope/SCOPE_P_Rohith.md 2, component 4
"""

from __future__ import annotations

import math
from typing import Final

import pandas as pd

from pramana.analysis.config import HypothesesConfig
from pramana.analysis.hypotheses.base import ClaimScreen, emit, usable_pair
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile
from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType, Direction

#: Hedged wording. A trend claim is still an association claim; "rises with" would
#: overstate what a rank test can support.
CLAIM_TEMPLATE: Final = "{y} is associated with {x}"

STRATEGY_NAME: Final = "trend"


def _as_ordered_numeric(series: pd.Series) -> pd.Series:
    """A time axis as a number, preserving order.

    Timestamps become nanoseconds since the epoch. Only the ORDER matters to a rank
    correlation, so the unit is irrelevant and the conversion is lossless for the
    purpose it serves.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.astype("int64")
    return pd.to_numeric(series, errors="coerce")


def propose(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    config: HypothesesConfig,
    *,
    dataset_ref: str,
    claim_screen: ClaimScreen | None = None,
) -> list[CandidateInsight]:
    """Propose a trend candidate for every time axis x measure worth testing.

    Guarantees: `variables` is `[time_axis, measure]` in that order, matching how the
    gateway's trend template unpacks it; the pair had at least
    `config.min_observations` complete rows; and `|tau-b| >= config.min_abs_trend_tau`
    as an exploratory hint only. A frame with no time-like column returns an empty
    list rather than substituting an arbitrary ordering.
    """
    time_axes = [
        name
        for name, profile in schema.columns.items()
        if profile.usable_for_hypotheses and profile.is_time_like
    ]
    measures = schema.usable(ColumnRole.NUMERIC)
    candidates: list[CandidateInsight] = []

    for x_column in time_axes:
        for y_column in measures:
            if x_column == y_column:
                continue
            pair = usable_pair(frame, x_column, y_column, config.min_observations)
            if pair is None:
                continue

            axis = _as_ordered_numeric(pair[x_column])
            ordered = pd.DataFrame({x_column: axis, y_column: pair[y_column]}).dropna()
            if len(ordered) < config.min_observations or ordered[x_column].nunique() < 2:
                continue

            tau = ordered[x_column].corr(ordered[y_column], method="kendall")
            if tau is None or math.isnan(tau) or abs(tau) < config.min_abs_trend_tau:
                continue

            candidate = emit(
                strategy=STRATEGY_NAME,
                claim=CLAIM_TEMPLATE.format(y=y_column, x=x_column),
                claim_type=ClaimType.TREND,
                variables=[x_column, y_column],
                dataset_ref=dataset_ref,
                direction=Direction.POSITIVE if tau > 0 else Direction.NEGATIVE,
                evidence={
                    "stat": "kendall_tau_b",
                    "raw_value": float(tau),
                    "n_observations": int(len(ordered)),
                    "source": "exploratory scan; not a test result",
                },
                claim_screen=claim_screen,
            )
            if candidate is not None:
                candidates.append(candidate)

    return candidates
