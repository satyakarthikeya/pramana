"""What a column means to an analyst, read from its name and values.

A data scientist does not treat every numeric column alike: a count can be summed across
groups, an age or a rate cannot; one column is usually the outcome the table was collected
for; some columns are the same fact written twice (`class` and `pclass`) or the outcome
itself under another name (`alive` beside `survived`). These helpers make those calls with
plain rules so the rest of the analysis can lean on them. They never decide a statistic.
"""

from __future__ import annotations

import re

import pandas as pd

#: Name words for quantities that add up across rows, groups and periods.
_ADDITIVE = {
    "count",
    "counts",
    "number",
    "num",
    "qty",
    "quantity",
    "units",
    "sales",
    "revenue",
    "amount",
    "cost",
    "costs",
    "spend",
    "spending",
    "passengers",
    "visitors",
    "orders",
    "transactions",
    "volume",
    "total",
    "sum",
    "deaths",
    "cases",
    "births",
    "population",
    "profit",
    "profits",
    "turnover",
    "bookings",
    "visits",
    "clicks",
    "views",
    "sold",
}
#: Name words for quantities that are averaged, never summed.
_NON_ADDITIVE = {
    "rate",
    "rates",
    "ratio",
    "pct",
    "percent",
    "percentage",
    "share",
    "avg",
    "average",
    "mean",
    "median",
    "per",
    "capita",
    "index",
    "score",
    "age",
    "expectancy",
    "price",
    "temperature",
    "temp",
    "bmi",
    "density",
    "margin",
    "probability",
    "prob",
    "speed",
    "height",
    "weight",
    "length",
    "diameter",
    "width",
    "level",
    "grade",
    "rating",
}

#: Names that usually mean "this is what the table is about" (the outcome).
_TARGET_NAMES = (
    "target",
    "label",
    "outcome",
    "y",
    "survived",
    "survival",
    "churn",
    "churned",
    "default",
    "defaulted",
    "converted",
    "conversion",
    "purchased",
    "clicked",
    "fraud",
    "is_fraud",
    "diagnosis",
    "response",
    "result",
    "attrition",
    "readmitted",
    "approved",
    "passed",
    "won",
    "success",
    "status",
    "class_label",
    "price",
    "rings",
    "quality",
    "total",
    "sales",
    "revenue",
)


def words(name: str) -> list[str]:
    """The lower-case words of a column name: `Whole_weight` -> ["whole", "weight"]."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(name))
    return [w for w in re.split(r"[^a-zA-Z0-9]+", spaced.lower()) if w]


def is_additive(name: str) -> bool:
    """Whether totals of this column mean something. Unknown names are averaged (safe)."""
    tokens = set(words(name))
    if tokens & _NON_ADDITIVE:
        return False
    return bool(tokens & _ADDITIVE)


def is_binary(series: pd.Series) -> bool:
    """Two distinct values (0/1, yes/no, True/False), ignoring missing ones."""
    return series.dropna().nunique() == 2


def as_binary(series: pd.Series) -> pd.Series | None:
    """A 0/1 float version of a two-valued column, with 1 for the "positive" level."""
    present = series.dropna()
    levels = list(pd.unique(present))
    if len(levels) != 2:
        return None
    positive_words = {
        "1",
        "true",
        "yes",
        "y",
        "survived",
        "alive",
        "pass",
        "passed",
        "won",
        "positive",
        "churn",
        "churned",
        "default",
        "fraud",
        "success",
    }
    keyed = {str(v).strip().lower(): v for v in levels}
    positive = next((keyed[k] for k in keyed if k in positive_words), None)
    if positive is None:
        try:
            positive = max(levels, key=float)
        except (TypeError, ValueError):
            positive = sorted(levels, key=str)[-1]
    out = series.map(lambda v: float(v == positive) if pd.notna(v) else float("nan"))
    return out.astype(float).rename(series.name)


def positive_label(series: pd.Series) -> str:
    """The level `as_binary` counts as 1, as text."""
    binary = as_binary(series)
    if binary is None:
        return ""
    return str(series[binary == 1.0].iloc[0]) if (binary == 1.0).any() else ""


def target_rank(name: str) -> int | None:
    """Position of the name in the outcome-name list (lower is likelier), or None."""
    tokens = words(name)
    joined = "_".join(tokens)
    for rank, candidate in enumerate(_TARGET_NAMES):
        if joined == candidate or (len(tokens) == 1 and tokens[0] == candidate):
            return rank
    return None


__all__ = [
    "as_binary",
    "is_additive",
    "is_binary",
    "positive_label",
    "target_rank",
    "words",
]
