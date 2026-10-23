"""Descriptive chart data computed by code from the user's own table.

Nothing here tests, scores or decides anything. Charts show the data a claim is about so a
person can see it; the verdict comes only from the proof object.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

from pramana.api.models import (
    Bin,
    CategoryCount,
    ChartSpec,
    ColumnOverview,
    CorrelationMatrix,
    DataOverview,
    GroupsChart,
    GroupSummary,
    ScatterChart,
)
from pramana.contracts import CandidateInsight, ClaimType

MAX_SCATTER_POINTS = 600
MAX_GROUP_POINTS = 150
MAX_GROUPS = 12
HISTOGRAM_BINS = 12
MAX_CATEGORIES = 8
MAX_CORRELATION_COLUMNS = 10


def _evenly(values: Sequence[float], limit: int) -> list[float]:
    """Pick up to `limit` values at fixed positions so the same data draws the same chart."""
    if len(values) <= limit:
        return [float(v) for v in values]
    index = np.linspace(0, len(values) - 1, limit).round().astype(int)
    return [float(values[i]) for i in index]


def _numeric(frame: pd.DataFrame, name: str) -> pd.Series:
    series = pd.to_numeric(frame[name], errors="coerce")
    return series.replace([np.inf, -np.inf], np.nan)


def claim_chart(candidate: CandidateInsight, frame: pd.DataFrame) -> ChartSpec | None:
    """Return the picture for one claim, or None when its columns cannot be drawn."""
    names = list(candidate.variables)
    if len(names) != 2 or any(name not in frame.columns for name in names):
        return None
    if candidate.claim_type in {ClaimType.CORRELATION, ClaimType.TREND}:
        x_name, y_name = names
        both = pd.DataFrame({"x": _numeric(frame, x_name), "y": _numeric(frame, y_name)}).dropna()
        if both.empty:
            return None
        both = both.sort_values(["x", "y"], kind="stable")
        count = min(len(both), MAX_SCATTER_POINTS)
        index = np.linspace(0, len(both) - 1, count).round().astype(int)
        shown = both.iloc[index]
        fit: list[tuple[float, float]] = []
        if len(both) >= 3 and both["x"].nunique() > 1:
            slope, intercept = np.polyfit(both["x"], both["y"], 1)
            lo, hi = float(both["x"].min()), float(both["x"].max())
            fit = [(lo, float(slope * lo + intercept)), (hi, float(slope * hi + intercept))]
        return ScatterChart(
            x=x_name,
            y=y_name,
            n=len(both),
            shown=len(shown),
            points=[(float(a), float(b)) for a, b in zip(shown["x"], shown["y"], strict=True)],
            fit=fit,
        )
    if candidate.claim_type is ClaimType.GROUP_DIFFERENCE:
        group_name, value_name = names
        both = pd.DataFrame(
            {"g": frame[group_name].astype("string"), "v": _numeric(frame, value_name)}
        ).dropna()
        if both.empty:
            return None
        counts = both["g"].value_counts()
        labels = sorted(counts.index[:MAX_GROUPS])
        groups = []
        for label in labels:
            values = np.sort(both.loc[both["g"] == label, "v"].to_numpy(dtype=float))
            groups.append(
                GroupSummary(
                    label=str(label),
                    n=len(values),
                    minimum=float(values[0]),
                    q1=float(np.percentile(values, 25)),
                    median=float(np.percentile(values, 50)),
                    q3=float(np.percentile(values, 75)),
                    maximum=float(values[-1]),
                    points=_evenly(values, MAX_GROUP_POINTS),
                )
            )
        return GroupsChart(
            value=value_name,
            group=group_name,
            n=int(sum(g.n for g in groups)),
            groups=groups,
        )
    return None


def _finite(value: float) -> float | None:
    return float(value) if math.isfinite(value) else None


def data_overview(frame: pd.DataFrame, usable: Sequence[str]) -> DataOverview:
    """Summarise the columns that can be analysed: spread, counts and descriptive correlations."""
    columns: list[ColumnOverview] = []
    numeric_names: list[str] = []
    for name in usable:
        if name not in frame.columns:
            continue
        raw = frame[name]
        numbers = _numeric(frame, name)
        n = int(raw.notna().sum())
        missing = int(len(raw) - n)
        if pd.api.types.is_numeric_dtype(raw) and numbers.notna().sum() > 0:
            clean = numbers.dropna()
            counts, edges = np.histogram(clean, bins=min(HISTOGRAM_BINS, max(1, clean.nunique())))
            columns.append(
                ColumnOverview(
                    name=name,
                    kind="numeric",
                    n=int(len(clean)),
                    missing=missing,
                    mean=_finite(float(clean.mean())),
                    median=_finite(float(clean.median())),
                    bins=[
                        Bin(x0=float(edges[i]), x1=float(edges[i + 1]), count=int(counts[i]))
                        for i in range(len(counts))
                    ],
                )
            )
            numeric_names.append(name)
        else:
            top = raw.dropna().astype(str).value_counts().head(MAX_CATEGORIES)
            columns.append(
                ColumnOverview(
                    name=name,
                    kind="category",
                    n=n,
                    missing=missing,
                    top=[CategoryCount(label=str(k), count=int(v)) for k, v in top.items()],
                )
            )
    correlations = None
    picked = numeric_names[:MAX_CORRELATION_COLUMNS]
    if len(picked) >= 2:
        matrix = frame[picked].apply(pd.to_numeric, errors="coerce").corr(method="spearman")
        correlations = CorrelationMatrix(
            columns=picked,
            values=[[_finite(float(matrix.loc[a, b])) for b in picked] for a in picked],
        )
    return DataOverview(rows=int(len(frame)), columns=columns, correlations=correlations)
