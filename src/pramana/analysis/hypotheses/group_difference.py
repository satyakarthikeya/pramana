"""Categorical x numeric -> group_difference candidates.

Variable order is load-bearing. The gateway's template groups by `VAR_X` and measures
`VAR_Y` (`falsification/templates.py`), and `variables` is unpacked positionally, so
`[grouping, measured]` is the only order that tests the sentence the claim makes.

`reference_group` is the other load-bearing field. For a two-level grouping the gate
computes a SIGNED Cliff's delta and orients it by putting `reference_group` first; a
claim that says "higher in urban" without naming `urban` can come back REFUTED purely
because the levels sorted the other way. This strategy therefore names the level whose
values sit higher, and words the claim about that level, so the sentence and the sign
agree by construction.

Three or more levels have no direction to assert -- "these groups differ" is not a
directed statement -- so no `reference_group` and no `asserted_direction` are set, and
the gate falls back to unsigned epsilon-squared.

Owner: P. Rohith (built by P.P. Satya Karthikeya -- team-agreed cross-module work)
Scope: scope/SCOPE_P_Rohith.md 2, component 4
"""

from __future__ import annotations

import math
from typing import Final

import pandas as pd

from pramana.analysis.config import HypothesesConfig
from pramana.analysis.hypotheses.base import ClaimScreen, emit
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile
from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType, Direction

#: Hedged wording for the two-level case: a tendency about a named level.
DIRECTED_CLAIM_TEMPLATE: Final = "{y} tends to be higher when {x} is {level}"

#: Hedged wording when there is no direction to assert.
UNDIRECTED_CLAIM_TEMPLATE: Final = "{y} tends to differ between {x} groups"

STRATEGY_NAME: Final = "group-difference"


def _eta_squared(groups: list[pd.Series]) -> float:
    """Share of `y`'s variance sitting between the groups rather than within them.

    An exploratory magnitude in `[0, 1]`, used only to decide whether a pair is worth
    proposing. It is NOT the statistic the gateway gates on -- that is a permuted
    epsilon-squared with a null distribution behind it. Returns 0.0 when the total
    sum of squares is zero, which is the honest answer for a constant column.
    """
    values = pd.concat(groups)
    grand_mean = values.mean()
    total = float(((values - grand_mean) ** 2).sum())
    if total <= 0.0:
        return 0.0
    between = float(sum(len(group) * (group.mean() - grand_mean) ** 2 for group in groups))
    return max(0.0, min(1.0, between / total))


def propose(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    config: HypothesesConfig,
    *,
    dataset_ref: str,
    claim_screen: ClaimScreen | None = None,
) -> list[CandidateInsight]:
    """Propose a group-difference candidate for every grouping x measure worth testing.

    Guarantees: every returned candidate names `[grouping, measured]` in that order;
    the grouping has between `config.min_group_levels` and `config.max_group_levels`
    levels that each carry at least `config.min_group_size` rows; at least
    `config.min_observations` rows survive in total; and the exploratory eta-squared
    clears `config.min_group_effect`. A two-level candidate always names the higher
    level in `reference_group` and asserts `POSITIVE`, so the claim's wording and the
    gate's signed effect cannot disagree.

    Levels too small to compare are dropped from the comparison rather than merged.
    Merging would invent a group that is not in the data; dropping shrinks the claim
    to the levels that can actually carry it.
    """
    groupings = schema.usable(ColumnRole.CATEGORICAL, ColumnRole.ORDINAL)
    measures = schema.usable(ColumnRole.NUMERIC)
    candidates: list[CandidateInsight] = []

    for x_column in groupings:
        for y_column in measures:
            if x_column == y_column:
                continue
            candidate = _propose_one(
                frame,
                x_column,
                y_column,
                config,
                dataset_ref=dataset_ref,
                claim_screen=claim_screen,
            )
            if candidate is not None:
                candidates.append(candidate)

    return candidates


def _propose_one(
    frame: pd.DataFrame,
    x_column: str,
    y_column: str,
    config: HypothesesConfig,
    *,
    dataset_ref: str,
    claim_screen: ClaimScreen | None,
) -> CandidateInsight | None:
    """One grouping/measure pair, or `None` if it fails any fail-closed floor."""
    pair = frame[[x_column, y_column]].dropna()
    if pair.empty:
        return None

    labels = pair[x_column].astype(str)
    counts = labels.value_counts()
    kept = sorted(str(level) for level, size in counts.items() if size >= config.min_group_size)
    if not (config.min_group_levels <= len(kept) <= config.max_group_levels):
        return None

    pair = pair.loc[labels.isin(kept)]
    if len(pair) < config.min_observations:
        return None

    if pair[y_column].nunique() < 2:
        # A constant measure differs between no groups at all. Proposing it would
        # spend a correction slot on an arithmetic certainty.
        return None

    grouped = pair.groupby(pair[x_column].astype(str), observed=True)[y_column]
    groups = [grouped.get_group(level) for level in kept]

    effect = _eta_squared(groups)
    if math.isnan(effect) or effect < config.min_group_effect:
        return None

    medians = {level: float(group.median()) for level, group in zip(kept, groups, strict=True)}
    if len(kept) == 2:
        higher = max(medians, key=lambda level: medians[level])
        claim = DIRECTED_CLAIM_TEMPLATE.format(y=y_column, level=higher, x=x_column)
        direction: Direction | None = Direction.POSITIVE
        reference_group: str | None = higher
    else:
        claim = UNDIRECTED_CLAIM_TEMPLATE.format(y=y_column, x=x_column)
        direction = None
        reference_group = None

    return emit(
        strategy=STRATEGY_NAME,
        claim=claim,
        claim_type=ClaimType.GROUP_DIFFERENCE,
        variables=[x_column, y_column],
        dataset_ref=dataset_ref,
        direction=direction,
        reference_group=reference_group,
        evidence={
            "stat": "eta_squared",
            "raw_value": effect,
            "n_observations": int(len(pair)),
            "group_levels": kept,
            "group_medians": medians,
            "source": "exploratory scan; not a test result",
        },
        claim_screen=claim_screen,
    )
