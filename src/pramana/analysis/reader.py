"""The Data Reader: what is in this table, and what to double-check before trusting it.

Code reads the table and reports facts with the numbers behind them. It never edits data
and never decides anything statistical: a note is a prompt for a person to look, with a
suggested action, and every number in it was counted from the data.
"""

from __future__ import annotations

import re
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis import codebook
from pramana.analysis.schema_inference import ColumnProfile, ColumnRole, SchemaProfile

MIN_ROWS_FOR_SHAPE_CHECKS = 30
HIGH_MISSING = 0.20
SOME_MISSING = 0.05
SKEW_LIMIT = 2.0
OUTLIER_FENCE = 3.0  # multiples of the IQR beyond the quartiles
SENTINELS = (-9, -8, -7, -1, 7, 9, 77, 88, 99, 777, 888, 999, 7777, 9999, 99999)
_UNIT = re.compile(
    r"(?:^|_)(kg|cm|mm|mg|mgdl|mmhg|pct|percent|bpm|yrs?|years?|hrs?|hours?|lbs?)(?:_|$)",
    re.IGNORECASE,
)

Kind = Literal[
    "coded_missing",
    "possible_missing_code",
    "constant",
    "id_like",
    "high_missing",
    "some_missing",
    "outliers",
    "skewed",
    "two_level_code",
    "stored_as_text",
    "time_axis",
    "unit_hint",
    "few_rows",
]


class ColumnNote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Kind
    #: "check" means a person should look before trusting results; "note" is context.
    level: Literal["note", "check"]
    message: str
    suggestion: str | None = None
    evidence: dict[str, float | int | str] = Field(default_factory=dict)


class ColumnBrief(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    role: str
    usable: bool
    label: str | None = None
    unit: str | None = None
    coding: dict[str, str] | None = None
    notes: list[ColumnNote]


class DataBrief(BaseModel):
    """Counted from the data by code; no model was involved."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    headline: str
    columns_to_check: int = Field(ge=0)
    #: Columns whose names follow a known survey convention (their label, unit and coding
    #: are filled in). A hint to confirm against the survey documentation, never a fact.
    recognised: int = Field(default=0, ge=0)
    columns: list[ColumnBrief]


def _number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def _fmt(value: float) -> str:
    return f"{value:g}"


def _sentinel_notes(
    name: str, numbers: pd.Series, known: codebook.Variable | None
) -> list[ColumnNote]:
    """Codes that stand for 'refused' or 'unknown' but would be read as measurements."""
    notes: list[ColumnNote] = []
    n = len(numbers)
    stated = {
        code: meaning
        for code, meaning in (known.coding if known and known.coding else {}).items()
        if meaning in codebook.REFUSED_DONT_KNOW.values()
    }
    for code in SENTINELS:
        hits = int((numbers == code).sum())
        if hits == 0:
            continue
        evidence = {"value": code, "rows": hits, "share_pct": round(100 * hits / n, 2)}
        if str(code) in stated:
            notes.append(
                ColumnNote(
                    kind="coded_missing",
                    level="check",
                    message=f'{hits} rows hold {_fmt(code)}, which means "{stated[str(code)]}" '
                    "in this variable's coding, not a measurement.",
                    suggestion="Recode these to missing before analysing, or the code will be "
                    "read as a real value.",
                    evidence=evidence,
                )
            )
        elif known is None or known.coding is None:
            # Without a stated coding, only a value separated from all the others by a real
            # gap is suspicious: 99 in a column running 70 to 98 is just data.
            others = numbers[numbers != code]
            if n < MIN_ROWS_FOR_SHAPE_CHECKS or hits < 3 or hits / n < 0.01 or len(others) < 20:
                continue
            low, high = float(others.min()), float(others.max())
            gap = max(1.0, 0.25 * (high - low))
            if not (code > high + gap if code > 0 else code < low - gap):
                continue
            notes.append(
                ColumnNote(
                    kind="possible_missing_code",
                    level="check",
                    message=f"{hits} rows hold {_fmt(code)}, beyond every other value. Surveys "
                    "often use such a value for refused or unknown answers.",
                    suggestion="Check the codebook. If it means missing, recode it before "
                    "analysing.",
                    evidence=evidence,
                )
            )
    return notes


def _numeric_shape_notes(numbers: pd.Series) -> list[ColumnNote]:
    notes: list[ColumnNote] = []
    n = len(numbers)
    if n < MIN_ROWS_FOR_SHAPE_CHECKS or numbers.nunique() < 3:
        return notes
    q1, q3 = numbers.quantile(0.25), numbers.quantile(0.75)
    iqr = q3 - q1
    if iqr > 0:
        low, high = q1 - OUTLIER_FENCE * iqr, q3 + OUTLIER_FENCE * iqr
        far = numbers[(numbers < low) | (numbers > high)]
        if len(far) >= 3 or len(far) / n >= 0.005:
            notes.append(
                ColumnNote(
                    kind="outliers",
                    level="note",
                    message=f"{len(far)} values lie far outside the middle of the data "
                    f"(beyond {OUTLIER_FENCE:g} interquartile ranges).",
                    suggestion="Check units and entry errors. The gateway's rank-based tests "
                    "are not thrown off by a few extreme values.",
                    evidence={
                        "rows": len(far),
                        "minimum": float(numbers.min()),
                        "maximum": float(numbers.max()),
                    },
                )
            )
    skew = float(numbers.skew())
    if np.isfinite(skew) and abs(skew) >= SKEW_LIMIT:
        notes.append(
            ColumnNote(
                kind="skewed",
                level="note",
                message=f"The values are strongly skewed (skewness {skew:.1f}), so the mean "
                "is a poor summary here; the median is steadier.",
                evidence={"skewness": round(skew, 2)},
            )
        )
    return notes


def _column_brief(name: str, series: pd.Series, profile: ColumnProfile) -> ColumnBrief:
    known = codebook.lookup(name)
    notes: list[ColumnNote] = []
    present = series.dropna()
    n_rows, n = len(series), len(present)

    if known is None and (match := _UNIT.search(name)):
        notes.append(
            ColumnNote(
                kind="unit_hint",
                level="note",
                message=f'The name suggests the unit "{match.group(1).lower()}".',
            )
        )

    if profile.role is ColumnRole.ID_LIKE:
        notes.append(
            ColumnNote(
                kind="id_like",
                level="note",
                message="Almost every value is different, so this looks like an identifier. "
                "It is left out of the analysis.",
            )
        )
    if n and present.nunique() <= 1:
        notes.append(
            ColumnNote(
                kind="constant",
                level="check",
                message="Every value is the same, so it cannot relate to anything.",
                suggestion="Remove the column or check the export.",
            )
        )
    if n_rows:
        missing = 1 - n / n_rows
        if missing >= HIGH_MISSING:
            notes.append(
                ColumnNote(
                    kind="high_missing",
                    level="check",
                    message=f"{n_rows - n} of {n_rows} values are missing "
                    f"({100 * missing:.0f}%). Any claim about this column rests on the "
                    "rows that have it.",
                    suggestion="Check whether the gaps are random or follow a pattern.",
                    evidence={"missing": n_rows - n, "share_pct": round(100 * missing, 1)},
                )
            )
        elif missing >= SOME_MISSING:
            notes.append(
                ColumnNote(
                    kind="some_missing",
                    level="note",
                    message=f"{n_rows - n} of {n_rows} values are missing ({100 * missing:.0f}%).",
                    evidence={"missing": n_rows - n, "share_pct": round(100 * missing, 1)},
                )
            )
    if 0 < n < MIN_ROWS_FOR_SHAPE_CHECKS:
        notes.append(
            ColumnNote(
                kind="few_rows",
                level="check",
                message=f"Only {n} rows have a value, too few to say much.",
                evidence={"rows": n},
            )
        )

    numbers = _number(present)
    stored_as_text = pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)
    if stored_as_text and n >= MIN_ROWS_FOR_SHAPE_CHECKS and len(numbers) / n >= 0.9:
        notes.append(
            ColumnNote(
                kind="stored_as_text",
                level="note",
                message=f"{len(numbers)} of {n} values are numbers stored as text.",
                suggestion="Convert the column to numbers if it is a measurement.",
                evidence={"numeric_rows": len(numbers), "rows": n},
            )
        )
    if pd.api.types.is_numeric_dtype(series) or (len(numbers) == n and n > 0):
        notes.extend(_sentinel_notes(name, numbers, known))
        if profile.role is ColumnRole.NUMERIC:
            notes.extend(_numeric_shape_notes(numbers))
        if profile.role in {ColumnRole.ORDINAL, ColumnRole.CATEGORICAL} and numbers.nunique() == 2:
            values = ", ".join(_fmt(v) for v in sorted(numbers.unique()))
            notes.append(
                ColumnNote(
                    kind="two_level_code",
                    level="note",
                    message=f"Two values ({values}). Treated as a category, not a measurement.",
                )
            )
    if profile.is_time_like:
        notes.append(
            ColumnNote(
                kind="time_axis",
                level="note",
                message="Read as a time axis, so trends can be tested against it.",
            )
        )
    return ColumnBrief(
        name=name,
        role=profile.role.value,
        usable=profile.usable_for_hypotheses,
        label=known.label if known else None,
        unit=known.unit if known else None,
        coding=known.coding if known else None,
        notes=notes,
    )


def read_data(frame: pd.DataFrame, schema: SchemaProfile) -> DataBrief:
    """Describe every column in `frame` with counted facts and things worth checking."""
    columns = [
        _column_brief(name, frame[name], profile)
        for name, profile in schema.columns.items()
        if name in frame.columns
    ]
    to_check = sum(1 for column in columns if any(note.level == "check" for note in column.notes))
    numeric = sum(1 for c in columns if c.role == ColumnRole.NUMERIC.value)
    coded = sum(
        1 for c in columns if c.role in {ColumnRole.CATEGORICAL.value, ColumnRole.ORDINAL.value}
    )
    unused = sum(1 for c in columns if not c.usable)
    headline = (
        f"{len(frame):,} rows and {len(columns)} columns: {numeric} numeric, {coded} "
        f"categorical or coded, {unused} not used for analysis. "
        + (
            f"{to_check} column{'s' if to_check != 1 else ''} worth a closer look."
            if to_check
            else "Nothing needs a closer look."
        )
    )
    recognised = sum(1 for c in columns if c.label)
    return DataBrief(
        headline=headline, columns_to_check=to_check, recognised=recognised, columns=columns
    )
