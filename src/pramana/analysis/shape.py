"""What kind of table this is, which decides which analyses are valid (PLAN §4.1, D12).

  * cross_section -- no time axis (a survey, NHANES).
  * time_series   -- a time axis with at most one row per period (monthly P&L).
  * panel         -- time x entity with at most one row per pair (sales per region per month).
  * transactions  -- a time axis with many rows per period (invoices, ledger lines).

Deterministic, from the schema and the values. The result is shown to the user, so a
wrong guess is visible and can be corrected.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.schema_inference import ColumnRole, SchemaProfile, parse_timestamps

Period = Literal["day", "week", "month", "quarter", "year", "index"]

#: Cycle length per period, for counting complete seasonal cycles.
_CYCLE: dict[str, int] = {"month": 12, "quarter": 4}

#: Plausible calendar years, so an integer `year` column reads as time and an integer
#: age or count does not.
_YEAR_RANGE = (1800, 2200)

#: A grouping column with more levels than this is not treated as the panel's entity.
MAX_ENTITY_LEVELS = 50


class DataShape(StrEnum):
    CROSS_SECTION = "cross_section"
    TIME_SERIES = "time_series"
    PANEL = "panel"
    TRANSACTIONS = "transactions"


class ShapeProfile(BaseModel):
    """The table's shape and the columns that define it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shape: DataShape
    time_column: str | None = None
    entity_column: str | None = None
    period: Period | None = None
    n_periods: int = Field(default=0, ge=0)
    full_cycles: int = Field(
        default=0, ge=0, description="Complete years of monthly or quarterly periods."
    )
    reasons: list[str] = Field(min_length=1)


def _is_year_column(name: str, series: pd.Series) -> bool:
    lowered = name.lower()
    if not ("year" in lowered or lowered.endswith("yr") and len(lowered) <= 4):
        return False
    values = pd.to_numeric(series, errors="coerce").dropna()
    return (
        not values.empty
        and bool((values % 1 == 0).all())
        and bool(values.between(*_YEAR_RANGE).all())
    )


def time_column(
    frame: pd.DataFrame, schema: SchemaProfile, roles: dict[str, str] | None = None
) -> str | None:
    """The table's time axis: a datetime column first, then a time-named ordered column.

    A column the sector already explains (a survey weight named `WTMEC2YR` contains
    "yr") is never the time axis, and an ordered axis needs at least three levels.
    """
    roles = roles or {}
    datetimes = [n for n, p in schema.columns.items() if p.role is ColumnRole.DATETIME]
    if datetimes:
        return datetimes[0]
    for name, profile in schema.columns.items():
        if name in roles or name not in frame.columns:
            continue
        if (profile.is_time_like and profile.n_unique >= 3) or _is_year_column(name, frame[name]):
            return name
    return None


def period_keys(
    frame: pd.DataFrame, column: str, schema: SchemaProfile
) -> tuple[pd.Series, Period]:
    """One sortable period label per row, and the period it represents.

    Datetimes become calendar periods ("2025-03" for a month); a daily or weekly
    series longer than ~6 months is rolled up to months so totals are comparable.
    Ordered non-date axes (a `year` or `wave` column) are used as they are.
    """
    profile = schema.columns.get(column)
    if profile is not None and profile.role is ColumnRole.DATETIME:
        stamps = parse_timestamps(frame[column])
        unique = np.sort(stamps.dropna().unique())
        gaps = (
            np.diff(unique).astype("timedelta64[D]").astype(float)
            if len(unique) > 1
            else np.array([1.0])
        )
        step = float(np.median(gaps))
        span = (
            float((unique[-1] - unique[0]).astype("timedelta64[D]").astype(float))
            if len(unique) > 1
            else 0.0
        )
        period: Period
        if step <= 1.5:
            period = "day"
        elif step <= 8:
            period = "week"
        elif step <= 35:
            period = "month"
        elif step <= 100:
            period = "quarter"
        else:
            period = "year"
        if period in {"day", "week"} and span > 183:
            period = "month"
        code = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}[period]
        keys = stamps.dt.to_period(code).astype(str).where(stamps.notna())
        return keys, period
    values = pd.to_numeric(frame[column], errors="coerce")
    if _is_year_column(column, frame[column]):
        # whole years, even when a gap made pandas read the column as float ("2023.0")
        return values.round().astype("Int64"), "year"
    return values, "index"


def _full_cycles(keys: pd.Series, period: Period) -> int:
    length = _CYCLE.get(period)
    if length is None:
        return 0
    years = keys.dropna().astype(str).str[:4]
    distinct = keys.dropna().astype(str).groupby(years).nunique()
    return int((distinct >= length).sum())


def entity_column(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    roles: dict[str, str] | None = None,
    exclude: str | None = None,
) -> str | None:
    """The column that names WHO or WHERE: a sector `entity` role first, then a grouping."""
    roles = roles or {}
    candidates = [
        name
        for name, profile in schema.columns.items()
        if name != exclude
        and name in frame.columns
        and (
            profile.role in {ColumnRole.CATEGORICAL, ColumnRole.ID_LIKE}
            # a column the sector pack names as an entity (country, store, branch) is one
            # even with more levels than the general categorical cap (e.g. 43 countries)
            or (profile.role is ColumnRole.UNKNOWN and roles.get(name) == "entity")
        )
        and 2 <= frame[name].nunique(dropna=True) <= MAX_ENTITY_LEVELS
        # an identifier unique to every row names a record, not a group
        and frame[name].nunique(dropna=True) < frame[name].notna().sum()
    ]
    preferred = [name for name in candidates if roles.get(name) == "entity"]
    return (preferred or candidates or [None])[0]


def classify_shape(
    frame: pd.DataFrame, schema: SchemaProfile, roles: dict[str, str] | None = None
) -> ShapeProfile:
    """Classify the table. Guarantees: deterministic; `reasons` says why."""
    time = time_column(frame, schema, roles)
    if time is None:
        return ShapeProfile(shape=DataShape.CROSS_SECTION, reasons=["no date or period column"])
    keys, period = period_keys(frame, time, schema)
    n_periods = int(keys.nunique(dropna=True))
    cycles = _full_cycles(keys, period)
    common = {"time_column": time, "period": period, "n_periods": n_periods, "full_cycles": cycles}
    per_period = keys.value_counts(dropna=True)
    if per_period.empty or int(per_period.max()) <= 1:
        return ShapeProfile(
            shape=DataShape.TIME_SERIES, reasons=[f"one row per {period} in {time}"], **common
        )
    entity = entity_column(frame, schema, roles, exclude=time)
    if entity is not None:
        pairs = pd.DataFrame({"k": keys, "e": frame[entity]}).dropna().value_counts()
        if int(pairs.max()) <= 1:
            return ShapeProfile(
                shape=DataShape.PANEL,
                entity_column=entity,
                reasons=[f"one row per {period} and {entity}"],
                **common,
            )
    return ShapeProfile(
        shape=DataShape.TRANSACTIONS,
        entity_column=entity,
        reasons=[f"several rows per {period} in {time}"],
        **common,
    )
