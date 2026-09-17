"""Pairwise numeric correlation candidate generation."""

from __future__ import annotations

import pandas as pd

from pramana.contracts import CandidateInsight
from pramana.contracts.enums import ClaimType, Direction

from .base import insight_id, valid_pair


def generate_correlation_candidates(
    dataframe: pd.DataFrame, schema: dict[str, list[str]], dataset_ref: str
) -> list[CandidateInsight]:
    """Propose one unverified candidate for each usable numeric pair."""

    numeric = schema.get("numeric", [])
    candidates: list[CandidateInsight] = []
    for index, left in enumerate(numeric):
        for right in numeric[index + 1 :]:
            pair = valid_pair(dataframe, [left, right])
            if pair.empty:
                continue
            value = float(pair[left].corr(pair[right], method="spearman"))
            candidates.append(
                CandidateInsight(
                    insight_id=insight_id(dataset_ref, "correlation", [left, right]),
                    claim=f"{right} is associated with {left}",
                    claim_type=ClaimType.CORRELATION,
                    variables=[left, right],
                    dataset_ref=dataset_ref,
                    analysis_evidence={"stat": "spearman_rho", "raw_value": value},
                    asserted_direction=(
                        Direction.POSITIVE if value >= 0 else Direction.NEGATIVE
                    ),
                )
            )
    return candidates
