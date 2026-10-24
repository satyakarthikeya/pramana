"""Small helpers shared by the Measured analyses."""

from __future__ import annotations

import math

import numpy as np

from pramana.analysis import codebook
from pramana.analysis.computed.models import Scalar
from pramana.analysis.measured.models import Kind, MeasuredItem

TITLES: dict[str, str] = {
    "driver_regression": "What a model can predict a measure from",
    "driver_classification": "What a model can tell a group apart from",
    "adjusted_association": "Association after holding other columns fixed",
    "segments": "Segments of rows",
    "anomalies": "Rows unusual in combination",
    "forecast": "Forecast",
    "threshold": "A threshold in the pattern",
    "components": "Columns that move together",
}


def clean(value: object) -> Scalar:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    return None if value is None else str(value)


def row(**fields: object) -> dict[str, Scalar]:
    return {key: clean(value) for key, value in fields.items()}


def not_run(
    kind: Kind, reason: str, target: str | None = None, *, features: list[str] | None = None
) -> MeasuredItem:
    suffix = f":{target}" if target else ""
    return MeasuredItem(
        id=f"{kind}{suffix}",
        kind=kind,
        status="not_run",
        title=TITLES[kind],
        reason=reason,
        target=target,
        features=features or [],
    )


def withheld_item(
    fields: dict[str, object], *, score: float, metric: str, cutoff: float, subject: str
) -> MeasuredItem:
    """A result whose held-out score is at or past the "too good to be true" cutoff.

    The score is kept in `values` (the sentence quotes it) but not as a result: the
    score, baseline, lift and spread fields are cleared.
    """
    values = {
        **dict(fields.get("values") or {}),
        "withheld_score": score,
        "too_good_cutoff": cutoff,
    }  # type: ignore[call-overload]
    return MeasuredItem(
        **{
            **fields,
            "status": "withheld",
            "reason": "Too good to be true; check whether a column restates the target.",
            "sentence": (
                f"Withheld: a held-out {metric} of {score:.3f} for {subject} is too good to be "
                f"true (cutoff {cutoff:.3f}), so it is not shown as a result. Check whether a "
                "column restates it."
            ),
            "baseline_score": None,
            "model_score": None,
            "lift": None,
            "spread": None,
            "values": {k: clean(v) for k, v in values.items()},
        }  # type: ignore[arg-type]
    )


def finite(values: list[float]) -> list[float]:
    return [v for v in values if v is not None and math.isfinite(v)]


def sd(values: list[float]) -> float:
    """Sample standard deviation; 0 for fewer than two values."""
    return float(np.std(values, ddof=1)) if len(values) > 1 else 0.0


def label(column: str) -> str:
    """A column named for a reader: the codebook's label with the column in brackets."""
    known = codebook.lookup(column)
    return f"{known.label.lower()} ({column})" if known else column
