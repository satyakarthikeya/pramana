"""Datetime-by-numeric trend candidate generation."""

from __future__ import annotations

import pandas as pd

from pramana.contracts import CandidateInsight
from pramana.contracts.enums import ClaimType, Direction

from .base import insight_id, valid_pair


def generate_trend_candidates(
    dataframe: pd.DataFrame, schema: dict[str, list[str]], dataset_ref: str
) -> list[CandidateInsight]:
    """Propose monotonic time associations without assigning a verdict."""

    candidates: list[CandidateInsight] = []
    for time_column in schema.get("datetime", []):
        parsed = pd.to_datetime(dataframe[time_column], errors="coerce")
        for value in schema.get("numeric", []):
            pair = pd.DataFrame({"time": parsed, "value": dataframe[value]}).dropna()
            if len(pair) < 3 or pair["time"].nunique() < 2 or pair["value"].nunique() < 2:
                continue
            timestamps = pair["time"].astype("int64")
            correlation = float(timestamps.corr(pair["value"], method="spearman"))
            candidates.append(
                CandidateInsight(
                    insight_id=insight_id(dataset_ref, "trend", [time_column, value]),
                    claim=f"{value} is associated with {time_column}",
                    claim_type=ClaimType.TREND,
                    variables=[time_column, value],
                    dataset_ref=dataset_ref,
                    analysis_evidence={
                        "stat": "spearman_time_correlation",
                        "raw_value": correlation,
                    },
                    asserted_direction=(
                        Direction.POSITIVE
                        if correlation >= 0
                        else Direction.NEGATIVE
                    ),
                )
            )
    return candidates
