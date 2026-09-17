"""Pairwise correlation scan -> correlation candidates.

Spearman, not Pearson, for the pre-filter. The gateway gates correlation claims on
Spearman's rho (`falsification/templates.py`), so screening on Pearson here would
select pairs on one statistic and test them on another -- a linear relationship with
one leverage point clears a Pearson filter and then dies under a rank test, having
consumed a slot in the BH family on the way.

Continuous numerics only. Ordinal columns are grouped over by the group-difference
strategy and, when they are a time axis, followed by the trend strategy; running all
three over the same pair would put three correlated tests of one relationship into a
correction that assumes they are separate hypotheses.

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

#: Hedged wording. "is associated with" is the phrasing the gateway's screen accepts
#: and the strongest thing a permutation test can support.
CLAIM_TEMPLATE: Final = "{y} is associated with {x}"

STRATEGY_NAME: Final = "correlation"


def propose(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    config: HypothesesConfig,
    *,
    dataset_ref: str,
    claim_screen: ClaimScreen | None = None,
) -> list[CandidateInsight]:
    """Propose a correlation candidate for every numeric pair worth testing.

    Guarantees: every returned candidate names two distinct, usable, continuous
    numeric columns; was computed from at least `config.min_observations`
    pairwise-complete rows; and carries `|rho| >= config.min_abs_correlation` as an
    exploratory hint, never as evidence of anything. A pair that is too thin, constant
    or below the floor produces no candidate at all rather than a weak one.

    The order of the output is the frame's column order, so the scan is reproducible.
    """
    numeric = schema.usable(ColumnRole.NUMERIC)
    candidates: list[CandidateInsight] = []

    for left_index, x_column in enumerate(numeric):
        for y_column in numeric[left_index + 1 :]:
            pair = usable_pair(frame, x_column, y_column, config.min_observations)
            if pair is None:
                continue

            rho = pair[x_column].corr(pair[y_column], method="spearman")
            if rho is None or math.isnan(rho) or abs(rho) < config.min_abs_correlation:
                continue

            candidate = emit(
                strategy=STRATEGY_NAME,
                claim=CLAIM_TEMPLATE.format(y=y_column, x=x_column),
                claim_type=ClaimType.CORRELATION,
                variables=[x_column, y_column],
                dataset_ref=dataset_ref,
                direction=Direction.POSITIVE if rho > 0 else Direction.NEGATIVE,
                evidence={
                    "stat": "spearman_rho",
                    "raw_value": float(rho),
                    "n_observations": int(len(pair)),
                    "source": "exploratory scan; not a test result",
                },
                claim_screen=claim_screen,
            )
            if candidate is not None:
                candidates.append(candidate)

    return candidates
