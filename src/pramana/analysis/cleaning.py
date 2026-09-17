"""Conservative dataframe cleaning with a complete audit report."""

from __future__ import annotations

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
            {"column": column, "reason": "duplicate column name"}
            for column in duplicate_columns
        )

    duplicate_rows = int(frame.duplicated().sum())
    if duplicate_rows:
        frame = frame.drop_duplicates().reset_index(drop=True)

    missing_detected = {
        str(column): int(count)
        for column, count in frame.isna().sum().items()
        if count
    }
    invalid_numeric: list[dict[str, Any]] = []
    for column in frame.columns:
        if pd.api.types.is_object_dtype(frame[column]):
            converted = pd.to_numeric(frame[column], errors="coerce")
            non_missing = frame[column].notna().sum()
            if non_missing and converted.notna().sum() == non_missing:
                frame[column] = converted
                conversions.append({"column": column, "to": str(frame[column].dtype)})
        if not pd.api.types.is_numeric_dtype(frame[column]):
            continue
        if column in numeric_ranges:
            lower, upper = numeric_ranges[column]
            invalid = int(
                ((frame[column] < lower) | (frame[column] > upper)).fillna(False).sum()
            )
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
        dominant_ratio = frame[column].value_counts(
            dropna=False, normalize=True
        ).iloc[0]
        if dominant_ratio >= near_constant_threshold:
            near_constant.append(
                {"column": column, "dominant_ratio": float(dominant_ratio)}
            )
        if unique_ratio >= high_cardinality_threshold:
            high_cardinality.append(
                {"column": column, "unique_ratio": float(unique_ratio)}
            )
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

    report = CleaningReport(
        original_shape=original_shape,
        final_shape=(len(frame), len(frame.columns)),
        columns_removed=removed,
        duplicate_rows_removed=duplicate_rows,
        type_conversions=conversions,
        missing_values_detected=missing_detected,
        missing_value_summary={
            str(column): int(count)
            for column, count in frame.isna().sum().items()
            if count
        },
        near_constant_columns=near_constant,
        high_cardinality_columns=high_cardinality,
        identifier_columns=identifiers,
        inconsistent_categorical_labels=inconsistent_labels,
        invalid_numeric_values=invalid_numeric,
    )
    return frame, report
