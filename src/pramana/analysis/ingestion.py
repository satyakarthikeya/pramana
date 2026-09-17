"""CSV/XLSX ingestion with explicit limits and dataset metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

SUPPORTED_FORMATS = frozenset({".csv", ".xlsx"})
DEFAULT_MISSING_MARKERS = ("?", "NA", "N/A", "NULL", "null", "")


class DatasetMetadata(BaseModel):
    """Facts collected from an input dataframe before cleaning."""

    model_config = ConfigDict(extra="forbid")

    file_name: str
    file_type: str
    rows: int
    columns: int
    column_names: list[str]
    inferred_data_types: dict[str, str]
    missing_values: dict[str, int]
    duplicate_rows: int
    memory_usage_bytes: int
    unique_values: dict[str, int]
    schema_: dict[str, dict[str, Any]] = Field(alias="schema")


def load_dataset(
    path: str | Path,
    *,
    max_rows: int = 200_000,
    max_file_mb: int = 100,
    csv_encoding: str = "utf-8",
    missing_markers: tuple[str, ...] = DEFAULT_MISSING_MARKERS,
) -> pd.DataFrame:
    """Load a bounded CSV/XLSX dataframe without modifying the source file."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Dataset file does not exist: {source}")
    if source.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError("Only CSV and XLSX files are supported")
    if source.stat().st_size > max_file_mb * 1024 * 1024:
        raise ValueError(f"Dataset exceeds the {max_file_mb} MB file limit")

    options = {"na_values": list(missing_markers), "keep_default_na": True}
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(
            source, encoding=csv_encoding, low_memory=False, **options
        )
    else:
        frame = pd.read_excel(source, engine="openpyxl", **options)
    if len(frame) > max_rows:
        raise ValueError(f"Dataset exceeds the {max_rows} row limit")
    return frame


def get_dataset_metadata(
    dataframe: pd.DataFrame,
    *,
    source_path: str | Path,
) -> DatasetMetadata:
    """Return JSON-serializable metadata for an ingested dataframe."""

    names = [str(name) for name in dataframe.columns]
    dtypes = {
        name: str(dtype)
        for name, dtype in zip(names, dataframe.dtypes, strict=True)
    }
    missing = {
        name: int(count)
        for name, count in zip(names, dataframe.isna().sum(), strict=True)
    }
    unique = {
        name: int(count)
        for name, count in zip(names, dataframe.nunique(dropna=False), strict=True)
    }
    schema = {
        name: {
            "dtype": dtypes[name],
            "nullable": missing[name] > 0,
            "missing_count": missing[name],
            "unique_count": unique[name],
        }
        for name in names
    }
    source = Path(source_path)
    return DatasetMetadata(
        file_name=source.name,
        file_type=source.suffix.lower().lstrip("."),
        rows=len(dataframe),
        columns=len(dataframe.columns),
        column_names=names,
        inferred_data_types=dtypes,
        missing_values=missing,
        duplicate_rows=int(dataframe.duplicated().sum()),
        memory_usage_bytes=int(dataframe.memory_usage(index=True, deep=True).sum()),
        unique_values=unique,
        schema=schema,
    )
