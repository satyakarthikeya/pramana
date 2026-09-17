"""Deterministic column classification used by the analysis entrypoint."""

from __future__ import annotations

import pandas as pd


def infer_schema(dataframe: pd.DataFrame) -> dict[str, list[str]]:
    """Classify columns without making any verification or truth judgment."""

    numeric = [str(column) for column in dataframe.select_dtypes(include="number").columns]
    datetime: list[str] = []
    categorical: list[str] = []
    identifier: list[str] = []
    ordinal: list[str] = []
    for column in dataframe.columns:
        name = str(column)
        if name in numeric:
            if dataframe[column].nunique(dropna=True) <= 20:
                ordinal.append(name)
        else:
            looks_temporal = any(
                token in name.casefold() for token in ("date", "time", "year", "month")
            )
            parsed = pd.to_datetime(dataframe[column], errors="coerce", format="mixed")
            if looks_temporal and len(dataframe) and parsed.notna().mean() >= 0.8:
                datetime.append(name)
            else:
                categorical.append(name)
        if dataframe[column].nunique(dropna=True) / max(len(dataframe), 1) >= 0.95:
            identifier.append(name)
    return {
        "numeric": numeric,
        "categorical": categorical,
        "datetime": datetime,
        "ordinal": ordinal,
        "identifier": identifier,
    }
