"""Conservative dataframe cleaning with a complete audit report."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict


class CleaningReport(BaseModel):
    """Records transformations and quality findings for one cleaned frame."""

    model_config = ConfigDict(extra="forbid")

    original_shape: tuple[int, int]
    final_shape: tuple[int, int]
    columns_removed: list[dict[str, str]]
    duplicate_rows_removed: int
    type_conversions: list[dict[str, str]]
    missing_values_detected: dict[str, int]
    missing_value_summary: dict[str, int]
    near_constant_columns: list[dict[str, Any]]
    high_cardinality_columns: list[dict[str, Any]]
    identifier_columns: list[dict[str, Any]]
    inconsistent_categorical_labels: list[dict[str, Any]]
    invalid_numeric_values: list[dict[str, Any]]


_THOUSANDS = re.compile(r"^\s*[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?\s*$")


def _as_numbers(series: pd.Series) -> pd.Series:
    """Numbers stored as text, including thousands commas ("1,200"); others become NaN.

    Commas are removed only when every present value is written as digits with comma
    groups of three, so a list such as "1,2" is never read as twelve. The result is a
    plain numpy dtype, never a nullable extension dtype that would carry `pd.NA`.
    """
    plain = series.astype(object).where(series.notna(), None)
    converted = pd.to_numeric(plain, errors="coerce")
    present = plain.dropna().astype(str)
    if len(present) and converted.notna().sum() < len(present):
        numeric = pd.to_numeric(present, errors="coerce").notna()
        if bool((present.str.match(_THOUSANDS) | numeric).all()):
            stripped = plain.map(lambda v: v.replace(",", "") if isinstance(v, str) else v)
            converted = pd.to_numeric(stripped, errors="coerce")
    return converted


def clean_dataset(
    dataframe: pd.DataFrame,
    *,
    near_constant_threshold: float = 0.99,
    high_cardinality_threshold: float = 0.50,
    identifier_threshold: float = 0.95,
    numeric_ranges: dict[str, tuple[float, float]] | None = None,
) -> tuple[pd.DataFrame, CleaningReport]:
    """Clean a copy, remove only unusable columns, and explain every mutation."""

    frame = dataframe.copy()
    original_shape = (len(frame), len(frame.columns))
    frame.columns = [str(column).strip() for column in frame.columns]
    removed: list[dict[str, str]] = []
    conversions: list[dict[str, str]] = []
    numeric_ranges = numeric_ranges or {}

    duplicate_columns = frame.columns[frame.columns.duplicated()].tolist()
    if duplicate_columns:
        frame = frame.loc[:, ~frame.columns.duplicated()]
        removed.extend(
            {"column": column, "reason": "duplicate column name"} for column in duplicate_columns
        )

    # Identical rows are a double entry only when the table identifies its records (an id
    # column). Without one they are usually different people or events that look alike
    # (two Titanic passengers with the same class, sex, age and fare), so they are kept.
    duplicate_rows = 0
    has_identifier = any(
        frame[c].nunique(dropna=True) >= 0.9 * len(frame) for c in frame.columns
    ) if len(frame) else False
    if has_identifier and frame.duplicated().any():
        duplicate_rows = int(frame.duplicated().sum())
        frame = frame.drop_duplicates().reset_index(drop=True)

    missing_detected = {
        str(column): int(count) for column, count in frame.isna().sum().items() if count
    }
    invalid_numeric: list[dict[str, Any]] = []
    for column in frame.columns:
        # pandas 3 reads text as the `str` dtype, not `object`; both hold numbers-as-text.
        if pd.api.types.is_object_dtype(frame[column]) or pd.api.types.is_string_dtype(
            frame[column]
        ):
            converted = _as_numbers(frame[column])
            non_missing = frame[column].notna().sum()
            if non_missing and converted.notna().sum() == non_missing:
                frame[column] = converted
                conversions.append({"column": column, "to": str(frame[column].dtype)})
        if not pd.api.types.is_numeric_dtype(frame[column]):
            continue
        if column in numeric_ranges:
            lower, upper = numeric_ranges[column]
            invalid = int(((frame[column] < lower) | (frame[column] > upper)).fillna(False).sum())
            if invalid:
                invalid_numeric.append(
                    {
                        "column": column,
                        "count": invalid,
                        "reason": f"outside inclusive range [{lower}, {upper}]",
                    }
                )

    near_constant: list[dict[str, Any]] = []
    high_cardinality: list[dict[str, Any]] = []
    identifiers: list[dict[str, Any]] = []
    inconsistent_labels: list[dict[str, Any]] = []
    row_count = max(len(frame), 1)
    for column in list(frame.columns):
        if frame[column].isna().all():
            frame = frame.drop(columns=column)
            removed.append({"column": column, "reason": "entirely missing"})
            continue
        if frame[column].nunique(dropna=False) <= 1:
            frame = frame.drop(columns=column)
            removed.append({"column": column, "reason": "constant column"})
            continue

        unique_ratio = frame[column].nunique(dropna=True) / row_count
        dominant_ratio = frame[column].value_counts(dropna=False, normalize=True).iloc[0]
        if dominant_ratio >= near_constant_threshold:
            near_constant.append({"column": column, "dominant_ratio": float(dominant_ratio)})
        if unique_ratio >= high_cardinality_threshold:
            high_cardinality.append({"column": column, "unique_ratio": float(unique_ratio)})
        if unique_ratio >= identifier_threshold:
            identifiers.append({"column": column, "unique_ratio": float(unique_ratio)})
        if pd.api.types.is_string_dtype(frame[column]):
            normalized = frame[column].dropna().astype(str).str.strip().str.casefold()
            variants = frame.loc[normalized.index, column].dropna().astype(str)
            for normalized_value, values in variants.groupby(normalized).unique().items():
                if len(values) > 1:
                    inconsistent_labels.append(
                        {
                            "column": column,
                            "normalized_value": normalized_value,
                            "variants": sorted(map(str, values)),
                        }
                    )

    built = _calendar_date(frame)
    if built is not None:
        frame[built.name] = built
        conversions.append({"column": str(built.name), "to": "date built from year and month"})

    report = CleaningReport(
        original_shape=original_shape,
        final_shape=(len(frame), len(frame.columns)),
        columns_removed=removed,
        duplicate_rows_removed=duplicate_rows,
        type_conversions=conversions,
        missing_values_detected=missing_detected,
        missing_value_summary={
            str(column): int(count) for column, count in frame.isna().sum().items() if count
        },
        near_constant_columns=near_constant,
        high_cardinality_columns=high_cardinality,
        identifier_columns=identifiers,
        inconsistent_categorical_labels=inconsistent_labels,
        invalid_numeric_values=invalid_numeric,
    )
    return frame, report


_MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
            ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
            ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}


def _calendar_date(frame: pd.DataFrame) -> pd.Series | None:
    """A monthly date from separate `year` and `month` columns, or None.

    Tables such as `year, month, passengers` hold a monthly time series, but neither
    column is a date, so the series was read as twelve "month" groups. Built only when the
    table has no date column already, both columns parse fully, and the name is free.
    """
    if any(pd.api.types.is_datetime64_any_dtype(frame[c]) for c in frame.columns):
        return None
    lowered = {str(c).strip().lower(): c for c in frame.columns}
    year_col, month_col = lowered.get("year"), lowered.get("month")
    if year_col is None or month_col is None or "date" in lowered:
        return None
    years = pd.to_numeric(frame[year_col], errors="coerce")
    raw = frame[month_col]
    months = pd.to_numeric(raw, errors="coerce")
    if months.isna().any():
        months = raw.astype(str).str.strip().str.lower().map(_MONTHS)
    if years.isna().any() or months.isna().any():
        return None
    if not (years.between(1000, 3000).all() and months.between(1, 12).all()):
        return None
    dates = pd.to_datetime(
        {"year": years.astype(int), "month": months.astype(int), "day": 1}, errors="coerce"
    )
    if dates.isna().any() or dates.duplicated().any():
        return None  # several rows per month: not one series; leave the table as it is
    return dates.rename("date")
