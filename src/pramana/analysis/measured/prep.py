"""Shared preparation for the models: which columns are eligible, how rows are split.

Guarantees: eligibility never looks at the target's values (a feature is dropped for being
mostly empty, constant or too wide, never for how it relates to the target); preprocessing
is a pipeline step, so it is fitted inside each training fold only; splits respect the
table's shape (time order, entity groups) so a score cannot borrow from the future or from
the same entity.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import (
    GroupKFold,
    KFold,
    StratifiedKFold,
    TimeSeriesSplit,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from pramana.analysis.measured.config import MeasuredConfig
from pramana.analysis.measured.models import Exclusion
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile
from pramana.analysis.shape import DataShape, ShapeProfile, period_keys

SplitKind = Literal["random", "group", "time"]

_NUMERIC_ROLES = {ColumnRole.NUMERIC, ColumnRole.ORDINAL}
_TEXT_ROLES = {ColumnRole.CATEGORICAL}


def num(series: pd.Series) -> pd.Series:
    """Numbers only; text and +-inf become missing."""
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def is_numeric_column(schema: SchemaProfile, name: str, frame: pd.DataFrame) -> bool:
    return schema.role_of(name) in _NUMERIC_ROLES and name in frame.columns


def is_text_column(schema: SchemaProfile, name: str, frame: pd.DataFrame) -> bool:
    return schema.role_of(name) in _TEXT_ROLES and name in frame.columns


def eligible_columns(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    candidates: list[str],
    *,
    config: MeasuredConfig,
) -> tuple[list[str], list[Exclusion]]:
    """Columns a model may use, in the order given, and why the others cannot be.

    Identifier-like and survey-weight columns are handled by the leakage lint, so they
    are passed through here untouched.
    """
    kept: list[str] = []
    out: list[Exclusion] = []
    for name in candidates:
        if name not in frame.columns:
            out.append(Exclusion(column=name, reason=f"{name} is not a column of the table."))
            continue
        role = schema.role_of(name)
        if role is ColumnRole.ID_LIKE:
            kept.append(name)
            continue
        numeric = role in _NUMERIC_ROLES
        if not numeric and role not in _TEXT_ROLES:
            out.append(Exclusion(column=name, reason=f"{name} is not a measurement or a label."))
            continue
        values = num(frame[name]) if numeric else frame[name]
        if float(values.isna().mean()) > config.max_missing_fraction:
            out.append(Exclusion(column=name, reason=f"{name} is mostly empty."))
        elif values.nunique(dropna=True) < 2:
            out.append(Exclusion(column=name, reason=f"{name} has one value, so it cannot help."))
        elif not numeric and values.nunique(dropna=True) > config.max_categorical_levels:
            out.append(Exclusion(column=name, reason=f"{name} has too many distinct labels."))
        else:
            kept.append(name)
    return kept, out


def feature_frame(frame: pd.DataFrame, schema: SchemaProfile, columns: list[str]) -> pd.DataFrame:
    """Numeric columns as floats, label columns as text with true missing values."""
    data: dict[str, pd.Series] = {}
    for name in columns:
        if schema.role_of(name) in _NUMERIC_ROLES:
            data[name] = num(frame[name]).astype(float)
        else:
            text = frame[name].astype("object")
            data[name] = text.where(frame[name].notna(), np.nan).map(
                lambda v: v if isinstance(v, float) and np.isnan(v) else str(v)
            )
    return pd.DataFrame(data, index=frame.index)


def preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    """Impute, then scale numbers and one-hot labels; fitted wherever the pipeline is."""
    numeric = [c for c in X.columns if pd.api.types.is_numeric_dtype(X[c])]
    labels = [c for c in X.columns if c not in numeric]
    parts = []
    if numeric:
        parts.append(
            (
                "num",
                Pipeline(
                    [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
                ),
                numeric,
            )
        )
    if labels:
        parts.append(
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                labels,
            )
        )
    return ColumnTransformer(parts, sparse_threshold=0.0)


@dataclass(frozen=True)
class Table:
    """Rows ready for modelling, in the order the split needs."""

    X: pd.DataFrame
    y: pd.Series
    groups: np.ndarray | None
    kind: SplitKind
    ordered_by: str | None


def held_out_blocker(shape: ShapeProfile) -> str | None:
    """Why rows of this table cannot be held out honestly, or None when they can.

    Several rows share each period in a transactions table, so a split by time would put
    rows of one period on both sides of a fold; the table would have to be aggregated per
    period first, which a forecast does and a row-level model does not.
    """
    if shape.shape is DataShape.TRANSACTIONS:
        return (
            "Rows of a transactions table share periods, so they cannot be held out in "
            "time order; see the forecast for the per-period view."
        )
    return None


@dataclass(frozen=True)
class Aggregated:
    """A transactions table rolled up to one row per period and entity."""

    frame: pd.DataFrame
    schema: SchemaProfile
    shape: ShapeProfile
    note: str


#: Sector roles whose values add up across rows (revenue, cost, units). Anything else is
#: averaged, because a price or a rate summed over rows means nothing.
_SUMMED_ROLES = {"amount", "cost", "profit", "quantity"}


def aggregate_transactions(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    roles: dict[str, str],
) -> Aggregated | None:
    """Roll a transactions table up to period x entity so rows can be held out whole.

    Guarantees: every row of one period and entity lands in exactly one aggregate row, so
    no period-entity cell is ever split between training and testing; additive measures
    are summed, other numbers averaged; a label column is kept only if it is constant
    within every cell. Returns None when the table has no entity or time column, or the
    roll-up would leave too few rows to model.
    """
    from pramana.analysis import infer_schema, load_config
    from pramana.analysis.shape import classify_shape

    time, entity = shape.time_column, shape.entity_column
    if shape.shape is not DataShape.TRANSACTIONS or not time or not entity:
        return None
    keys, _ = period_keys(frame, time, schema)
    cell = pd.DataFrame({"__period__": keys, "__entity__": frame[entity].astype(str)})
    valid = keys.notna() & frame[entity].notna()
    grouped = frame[valid].groupby([cell.loc[valid, "__period__"], cell.loc[valid, "__entity__"]])
    parts: dict[str, pd.Series] = {}
    for name in frame.columns:
        if name in (time, entity):
            continue
        role = schema.role_of(name)
        if role in _NUMERIC_ROLES:
            how = "sum" if roles.get(name) in _SUMMED_ROLES else "mean"
            parts[name] = grouped[name].apply(lambda s, h=how: getattr(num(s), h)())
        elif role in _TEXT_ROLES:
            constant = grouped[name].nunique(dropna=True).le(1).all()
            if constant:
                parts[name] = grouped[name].first()
    if not parts:
        return None
    out = pd.DataFrame(parts).reset_index()
    out = out.rename(columns={"__period__": time, "__entity__": entity})
    if len(out) < 30:
        return None
    new_schema = infer_schema(out, load_config().schema_inference)
    new_shape = classify_shape(out, new_schema, roles)
    note = (
        f"Fitted on totals per {shape.period or 'period'} and {entity} "
        f"({len(out):,} rows from {int(valid.sum()):,}), so rows that share a period are "
        "never split between training and testing."
    )
    return Aggregated(out, new_schema, new_shape, note)


def split_kind(shape: ShapeProfile) -> SplitKind:
    if shape.shape is DataShape.PANEL and shape.entity_column:
        return "group"
    if shape.shape in {DataShape.TIME_SERIES, DataShape.PANEL, DataShape.TRANSACTIONS}:
        return "time"
    return "random"


def build_table(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    features: list[str],
    y: pd.Series,
) -> Table:
    """Feature rows and target aligned, ordered by time for time shapes.

    Rows without a target value are dropped. Time and panel tables are sorted by period
    so earlier rows train and later rows test; panel tables also carry the entity as the
    group, so no entity is in both the training and the held-out part of a fold.
    """
    kind = split_kind(shape)
    X = feature_frame(frame, schema, features)
    keep = y.notna()
    order_name: str | None = None
    if shape.time_column is not None and kind in {"group", "time"}:
        keys, _ = period_keys(frame, shape.time_column, schema)
        keep &= keys.notna()
        index = keys[keep].sort_values(kind="stable").index
        order_name = shape.time_column
    else:
        index = frame.index[keep]
    groups = None
    if kind == "group":
        groups = frame.loc[index, shape.entity_column].astype(str).to_numpy()
    return Table(
        X=X.loc[index].reset_index(drop=True),
        y=y.loc[index].reset_index(drop=True),
        groups=groups,
        kind=kind,
        ordered_by=order_name,
    )


def outer_splitter(
    table: Table, config: MeasuredConfig, *, classification: bool
) -> tuple[object, str] | None:
    """The outer cross-validation object and its plain description, or None if the table
    cannot be split that way (too few entities or rows)."""
    k = config.outer_folds
    if table.kind == "time":
        if len(table.y) < (k + 1) * 5:
            return None
        return TimeSeriesSplit(n_splits=k), f"TimeSeriesSplit {k} folds"
    if table.kind == "group":
        assert table.groups is not None
        n_groups = len(set(table.groups))
        folds = min(k, n_groups)
        if folds < 3:
            return None
        return GroupKFold(n_splits=folds), f"GroupKFold {folds} folds by entity"
    if classification:
        return (
            StratifiedKFold(n_splits=k, shuffle=True, random_state=config.seed),
            f"{k}-fold stratified KFold",
        )
    return KFold(n_splits=k, shuffle=True, random_state=config.seed), f"{k}-fold KFold"


def inner_splitter(kind: SplitKind, n_groups: int | None, config: MeasuredConfig) -> object:
    """Cross-validation used inside a training part to pick between grid settings."""
    k = config.inner_folds
    if kind == "time":
        return TimeSeriesSplit(n_splits=k)
    if kind == "group":
        return GroupKFold(n_splits=max(2, min(k, n_groups or k)))
    return KFold(n_splits=k, shuffle=True, random_state=config.seed)


def folds(table: Table, cv: object) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    yield from cv.split(table.X, table.y, table.groups)  # type: ignore[attr-defined]
