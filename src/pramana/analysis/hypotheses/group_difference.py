"""Categorical-by-numeric group-difference candidate generation."""

from __future__ import annotations

import pandas as pd

from pramana.contracts import CandidateInsight
from pramana.contracts.enums import ClaimType, Direction

from .base import insight_id


def generate_group_difference_candidates(
    dataframe: pd.DataFrame, schema: dict[str, list[str]], dataset_ref: str
) -> list[CandidateInsight]:
    """Propose group differences using exploratory group means only."""

    candidates: list[CandidateInsight] = []
    for category in schema.get("categorical", []):
        for value in schema.get("numeric", []):
            pair = dataframe[[category, value]].dropna()
            means = pair.groupby(category, observed=True)[value].mean()
            if len(means) < 2:
                continue
            reference = str(means.idxmax())
            candidates.append(
                CandidateInsight(
                    insight_id=insight_id(
                        dataset_ref, "group_difference", [category, value]
                    ),
                    claim=f"{value} tends to be higher in {reference}",
                    claim_type=ClaimType.GROUP_DIFFERENCE,
                    variables=[category, value],
                    dataset_ref=dataset_ref,
                    analysis_evidence={
                        "stat": "group_mean_difference",
                        "raw_value": float(means.max() - means.min()),
                    },
                    asserted_direction=Direction.POSITIVE,
                    reference_group=reference,
                )
            )
    return candidates
