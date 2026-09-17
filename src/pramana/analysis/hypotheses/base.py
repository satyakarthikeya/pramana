"""Shared helpers for candidate-generating strategies."""

from __future__ import annotations

import hashlib

import pandas as pd

from pramana.contracts import CandidateInsight


def insight_id(dataset_ref: str, kind: str, variables: list[str]) -> str:
    """Return a stable, unique identifier for one dataset/strategy/column set."""

    value = "|".join((dataset_ref, kind, *variables))
    return f"{kind}-{hashlib.sha1(value.encode('utf-8')).hexdigest()[:16]}"


def valid_pair(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Return usable rows for a candidate pair, or an empty frame."""

    pair = dataframe[columns].dropna()
    if len(pair) < 3 or any(pair[column].nunique() < 2 for column in columns):
        return pair.iloc[0:0]
    return pair


def evidence_value(candidate: CandidateInsight) -> float:
    """Extract a finite ranking value from exploratory evidence."""

    value = candidate.analysis_evidence.get("raw_value", 0.0)
    return abs(float(value)) if isinstance(value, (int, float)) else 0.0
