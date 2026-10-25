"""The analyst's read of a table: what it is about, what drives it, what changed, what to doubt.

This follows the order a data scientist works in, with every number computed here by
pandas, never by a model:

1. **Understand the table**: how many rows, what one row is, the time axis and the entity
   (if any), and the outcome the table was most likely collected for.
2. **Clean the question**: columns that are the outcome under another name (leakage) or the
   same fact written twice (redundancy) are set aside, with the reason shown.
3. **Explain the outcome**: rank every other column by how strongly it goes with the
   outcome (rates or averages per group, top versus bottom quarter), then look for the
   pair of drivers that separates the outcome most sharply.
4. **Time and comparison**: growth, trend and seasonality of each measure, and how entities
   compare (including "highest on one measure, lowest on another").
5. **Relationships** among the other columns when there is no outcome, and **data
   quality** (missing values, skew) that changes how far to trust the rest.

Each insight may carry a structured claim. Those are what the verification gateway tests:
the insight is descriptive (Exact); only a claim that passes the gate becomes a finding.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.computed.charts import Bar, BarChart, ChartSpec, LineChart
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile
from pramana.analysis.semantics import as_binary, is_additive, positive_label, target_rank
from pramana.analysis.shape import classify_shape, period_keys
from pramana.common.logging import get_logger

INSIGHTS_VERSION = 1
Scalar = float | int | str | bool | None
Section = Literal["outcome", "drivers", "time", "comparison", "relationships", "quality"]

MAX_LEVELS = 12  # categorical levels shown or compared
MIN_LEVEL_ROWS = 10  # a level with fewer rows is not compared (its rate is mostly noise)
REDUNDANT = 0.95  # |rho| or Cramer's V at which two columns hold the same fact
LEAK = 0.98  # association with the outcome at which a column IS the outcome
WEAK = 0.10  # below this an association is not reported as a driver

logger = get_logger(component="insights")


class InsightClaim(BaseModel):
    """A structured claim for the gateway; the sentence is written later by code."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    claim_type: Literal["correlation", "group_difference", "trend"]
    variables: list[str]
    direction: Literal["positive", "negative"] | None = None
    reference_group: str | None = None


class Insight(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    section: Section
    title: str
    text: str
    importance: float = Field(ge=0)
    strength: float | None = None
    columns: list[str] = Field(default_factory=list)
    values: dict[str, Scalar] = Field(default_factory=dict)
    chart: ChartSpec | None = None
    claim: InsightClaim | None = None


class Target(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    column: str
    kind: Literal["binary", "numeric"]
    positive: str | None = None
    reason: str


class InsightReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: int = INSIGHTS_VERSION
    rows: int
    columns: int
    grain: str
    target: Target | None = None
    time_column: str | None = None
    entity_column: str | None = None
    period: str | None = None
    set_aside: list[str] = Field(default_factory=list)
    insights: list[Insight] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)

    def claims(self, limit: int) -> list[InsightClaim]:
        """The structured claims, strongest insight first, without repeats."""
        seen: set[tuple[str, tuple[str, ...]]] = set()
        out: list[InsightClaim] = []
        for insight in sorted(self.insights, key=lambda i: -i.importance):
            claim = insight.claim
            # A weak link costs every other claim some of the correction's room.
            if claim is None or (insight.strength is not None and insight.strength < 0.2):
                continue
            key = (claim.claim_type, tuple(sorted(claim.variables)))
            if key not in seen:
                seen.add(key)
                out.append(claim)
        return out[:limit]


# ---- number formatting -----------------------------------------------------------------


def _num(value: float) -> str:
    """A readable number: thousands separators, sensible decimals."""
    if value is None or not math.isfinite(value):
        return "n/a"
    magnitude = abs(value)
    if magnitude >= 1000 or float(value).is_integer():
        return f"{value:,.0f}"
    if magnitude >= 10:
        return f"{value:,.1f}"
    if magnitude >= 1:
        return f"{value:.2f}"
    return f"{value:.3g}"


def _pct(share: float) -> str:
    return f"{100 * share:.0f}%" if abs(share) >= 0.095 else f"{100 * share:.1f}%"


def _band(strength: float) -> str:
    return "strongly" if strength >= 0.5 else "moderately" if strength >= 0.3 else "weakly"


# ---- association measures (descriptive) -----------------------------------------------


def _cramers_v(a: pd.Series, b: pd.Series) -> float:
    table = pd.crosstab(a, b)
    if table.shape[0] < 2 or table.shape[1] < 2:
        return 0.0
    observed = table.to_numpy(dtype=float)
    total = observed.sum()
    expected = observed.sum(1, keepdims=True) * observed.sum(0, keepdims=True) / total
    chi2 = float(((observed - expected) ** 2 / np.where(expected == 0, 1, expected)).sum())
    k = min(table.shape) - 1
    return math.sqrt(chi2 / (total * k)) if total and k else 0.0


def _eta(values: pd.Series, groups: pd.Series) -> float:
    """Correlation ratio (sqrt of eta squared) of a numeric column across groups."""
    frame = pd.DataFrame({"v": values, "g": groups}).dropna()
    if frame["g"].nunique() < 2 or len(frame) < 3:
        return 0.0
    grand = frame["v"].mean()
    total = float(((frame["v"] - grand) ** 2).sum())
    between = float(
        sum(len(g) * (g.mean() - grand) ** 2 for _, g in frame.groupby("g", observed=True)["v"])
    )
    return math.sqrt(between / total) if total > 0 else 0.0


def _rho(a: pd.Series, b: pd.Series) -> float:
    pair = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(pair) < 5 or pair["a"].nunique() < 2 or pair["b"].nunique() < 2:
        return 0.0
    value = pair["a"].corr(pair["b"], method="spearman")
    return float(value) if pd.notna(value) else 0.0


# ---- understanding the table ----------------------------------------------------------


class _Columns:
    """Which columns are numbers, which are groups, which are left out, and why."""

    def __init__(self, frame: pd.DataFrame, schema: SchemaProfile, skip: set[str]) -> None:
        self.numeric: list[str] = []
        self.groups: list[str] = []
        for name, profile in schema.columns.items():
            if name not in frame.columns or name in skip or not profile.usable_for_hypotheses:
                continue
            distinct = frame[name].nunique(dropna=True)
            if (
                profile.role is ColumnRole.NUMERIC
                and distinct > 2
                or profile.role is ColumnRole.ORDINAL
                and distinct > MAX_LEVELS
            ):
                self.numeric.append(name)
            elif (
                profile.role
                in {
                    ColumnRole.CATEGORICAL,
                    ColumnRole.ORDINAL,
                    ColumnRole.NUMERIC,
                }
                and 2 <= distinct <= MAX_LEVELS
            ):
                self.groups.append(name)


def _pick_target(
    frame: pd.DataFrame,
    columns: _Columns,
    query: str | None,
    exclude: set[str],
) -> Target | None:
    candidates = [c for c in [*columns.numeric, *columns.groups] if c not in exclude]
    if not candidates:
        return None

    def build(column: str, reason: str) -> Target | None:
        if as_binary(frame[column]) is not None:
            return Target(
                column=column,
                kind="binary",
                positive=positive_label(frame[column]),
                reason=reason,
            )
        if column in columns.numeric:
            return Target(column=column, kind="numeric", reason=reason)
        return None

    if query:
        lowered = query.lower()
        named = [c for c in candidates if c.lower().replace("_", " ") in lowered.replace("_", " ")]
        for column in sorted(named, key=len, reverse=True):
            if found := build(column, "named in your question"):
                return found
    ranked = sorted(
        (rank, column) for column in candidates if (rank := target_rank(column)) is not None
    )
    for _, column in ranked:
        if found := build(column, "its name is a typical outcome"):
            return found
    last = [c for c in frame.columns if c in candidates]
    if last and len(columns.numeric) + len(columns.groups) >= 4:
        if found := build(last[-1], "the last column, where datasets usually keep the outcome"):
            return found
    return None


# ---- the report -----------------------------------------------------------------------


def build_insights(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    *,
    query: str | None = None,
    max_insights: int = 14,
) -> InsightReport:
    """Read the table like an analyst. Deterministic; each section fails on its own."""
    shape = classify_shape(frame, schema)
    time_column = shape.time_column
    entity = shape.entity_column if time_column else None
    built_from = {"year", "month", "day"} if time_column == "date" else set()
    skip = {time_column} if time_column else set()
    skip |= {c for c in frame.columns if str(c).lower() in built_from}
    columns = _Columns(frame, schema, skip)

    insights: list[Insight] = []
    set_aside: list[str] = []
    target = _pick_target(frame, columns, query, exclude={entity} if entity else set())

    sections = [
        lambda: _outcome(frame, target),
        lambda: _drivers(frame, columns, target, set_aside),
        lambda: _time(frame, schema, shape, columns, entity),
        lambda: _comparison(frame, schema, shape, columns, entity),
        lambda: _relationships(frame, columns, target, set_aside, time_column is not None),
        lambda: _quality(frame, columns),
    ]
    for section in sections:
        try:
            insights.extend(section())
        except Exception:
            logger.exception("insight_section_failed")
    insights.sort(key=lambda i: -i.importance)
    kept = insights[:max_insights]
    return InsightReport(
        rows=len(frame),
        columns=len(frame.columns),
        grain=_grain(shape, entity, frame),
        target=target,
        time_column=time_column,
        entity_column=entity,
        period=shape.period if time_column else None,
        set_aside=list(dict.fromkeys(set_aside)),
        insights=kept,
        questions=_questions(kept, target),
    )


def _grain(shape: object, entity: str | None, frame: pd.DataFrame) -> str:
    kind = getattr(shape, "shape", None)
    time_column, period = getattr(shape, "time_column", None), getattr(shape, "period", None)
    value = getattr(kind, "value", "cross_section")
    if value == "time_series":
        return f"One row per {period} ({time_column}), {len(frame):,} rows."
    if value == "panel" and entity:
        n = frame[entity].nunique()
        return f"One row per {entity} per {period}: {n} {entity} values over time."
    if value == "transactions":
        return f"Several rows per {period} in {time_column}: individual records over time."
    return f"One row per record, {len(frame):,} records, no time axis."


# ---- 1. the outcome --------------------------------------------------------------------


def _outcome(frame: pd.DataFrame, target: Target | None) -> list[Insight]:
    if target is None:
        return []
    column = target.column
    if target.kind == "binary":
        y = as_binary(frame[column])
        assert y is not None
        rate, n = float(y.mean()), int(y.notna().sum())
        return [
            Insight(
                id=f"outcome-{column}",
                section="outcome",
                title=f"Outcome: {column}",
                text=(
                    f"{_pct(rate)} of {n:,} rows have {column} = {target.positive} "
                    f"({int(y.sum()):,} rows). Everything below asks what goes with a higher "
                    f"or lower {column} rate."
                ),
                importance=100,
                columns=[column],
                values={"rate": round(rate, 4), "n": n},
            )
        ]
    y = pd.to_numeric(frame[column], errors="coerce").dropna()
    mean, median = float(y.mean()), float(y.median())
    skew = ""
    if y.std() > 0 and abs(mean - median) > 0.25 * y.std():
        skew = f" The mean sits {'above' if mean > median else 'below'} the median: a few {'large' if mean > median else 'small'} values pull it."
    return [
        Insight(
            id=f"outcome-{column}",
            section="outcome",
            title=f"Outcome: {column}",
            text=(
                f"{column} averages {_num(mean)} (median {_num(median)}, from {_num(y.min())} "
                f"to {_num(y.max())}, n = {len(y):,}).{skew} Everything below asks what goes "
                f"with a higher or lower {column}."
            ),
            importance=100,
            columns=[column],
            values={"mean": mean, "median": median, "n": int(len(y))},
        )
    ]


# ---- 2. drivers of the outcome --------------------------------------------------------


def _quartile_bins(x: pd.Series) -> pd.Series | None:
    try:
        bins = pd.qcut(x, 4, duplicates="drop")
    except ValueError:
        return None
    return bins if bins.cat.categories.size >= 2 else None


def _drivers(
    frame: pd.DataFrame, columns: _Columns, target: Target | None, set_aside: list[str]
) -> list[Insight]:
    if target is None:
        return []
    t = target.column
    y = as_binary(frame[t]) if target.kind == "binary" else pd.to_numeric(frame[t], errors="coerce")
    assert y is not None
    scored: list[tuple[float, str, str]] = []  # (strength, column, kind)
    for column in columns.groups:
        if column == t:
            continue
        labels = frame[column].astype("string")
        strength = _cramers_v(labels, y) if target.kind == "binary" else _eta(y, labels)
        scored.append((strength, column, "group"))
    for column in columns.numeric:
        if column == t:
            continue
        x = pd.to_numeric(frame[column], errors="coerce")
        strength = abs(_rho(x, y))
        scored.append((strength, column, "number"))

    # Leakage: a column that IS the outcome under another name explains nothing.
    leaks = [c for s, c, _ in scored if s >= LEAK]
    for column in leaks:
        set_aside.append(f"{column}: the same information as the outcome {t}, so it is left out")
    scored = [item for item in scored if item[1] not in leaks]

    # Redundancy: keep the stronger of two columns that hold the same fact.
    kept: list[tuple[float, str, str]] = []
    for item in sorted(scored, key=lambda s: -s[0]):
        twin = next((k for k in kept if _same_fact(frame, item[1], k[1])), None)
        if twin is None:
            kept.append(item)
            continue
        # Of two columns carrying nearly one split, an analyst leads with the simpler one
        # (sex over "man / woman / child") unless the other is clearly stronger.
        simpler = frame[item[1]].nunique() < frame[twin[1]].nunique()
        if simpler and item[0] >= twin[0] - 0.1:
            kept[kept.index(twin)] = item
            set_aside.append(f"{twin[1]}: holds nearly the same information as {item[1]}")
        else:
            set_aside.append(f"{item[1]}: holds nearly the same information as {twin[1]}")

    out: list[Insight] = []
    weak: list[str] = []
    for rank, (strength, column, kind) in enumerate(kept):
        if strength < WEAK:
            weak.append(column)
            continue
        if rank >= 6:
            continue
        importance = 90 - 4 * rank + 10 * strength
        built = (
            _group_driver(frame, column, y, target, strength, importance)
            if kind == "group"
            else _number_driver(frame, column, y, target, strength, importance)
        )
        if built is not None:
            out.append(built)
    if weak:
        out.append(
            Insight(
                id=f"weak-{t}",
                section="drivers",
                title="Little or no link to the outcome",
                text=(
                    f"{', '.join(weak[:6])} show little or no link to {t} on their own "
                    f"(strength under {WEAK})."
                ),
                importance=20,
                columns=weak[:6],
            )
        )
    if target.kind == "binary":
        if (pair := _independent_pair(frame, kept)) is not None:
            if (joint := _interaction(frame, pair, y, target)) is not None:
                out.append(joint)
    return out


def _independent_pair(frame: pd.DataFrame, kept: list[tuple[float, str, str]]) -> list[str] | None:
    """The two strongest group drivers that are not mostly the same split (V < 0.5).

    Sex with "who" (man, woman, child) would only restate one driver; sex with class shows
    how two separate facts combine.
    """
    groups = [c for s, c, k in kept if k == "group" and s >= WEAK]
    for i, a in enumerate(groups):
        for b in groups[i + 1 :]:
            if _cramers_v(frame[a].astype("string"), frame[b].astype("string")) < 0.5:
                return [a, b]
    return None


def _same_fact(frame: pd.DataFrame, a: str, b: str) -> bool:
    x, z = frame[a], frame[b]
    numeric = pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(z)
    if numeric and x.nunique() > MAX_LEVELS and z.nunique() > MAX_LEVELS:
        return abs(_rho(x, z)) >= REDUNDANT
    if x.nunique() <= MAX_LEVELS and z.nunique() <= MAX_LEVELS:
        return _cramers_v(x.astype("string"), z.astype("string")) >= REDUNDANT
    return False


def _levels(frame: pd.DataFrame, column: str, y: pd.Series) -> pd.DataFrame:
    table = (
        pd.DataFrame({"g": frame[column].astype("string"), "y": y})
        .dropna()
        .groupby("g", observed=True)["y"]
        .agg(["mean", "count"])
    )
    return table[table["count"] >= MIN_LEVEL_ROWS].sort_values("mean", ascending=False)


def _group_driver(
    frame: pd.DataFrame,
    column: str,
    y: pd.Series,
    target: Target,
    strength: float,
    importance: float,
) -> Insight | None:
    table = _levels(frame, column, y)
    if len(table) < 2:
        return None
    top, bottom = table.index[0], table.index[-1]
    t = target.column
    binary = target.kind == "binary"
    show = _pct if binary else _num
    measure = f"{t} rate" if binary else f"average {t}"
    text = (
        f"{measure[0].upper() + measure[1:]} differs {_band(strength)} by {column}: "
        f"{show(table.loc[top, 'mean'])} for {top} (n = {int(table.loc[top, 'count']):,}) "
        f"against {show(table.loc[bottom, 'mean'])} for {bottom} "
        f"(n = {int(table.loc[bottom, 'count']):,})."
    )
    if binary and table.loc[bottom, "mean"] > 0:
        ratio = table.loc[top, "mean"] / table.loc[bottom, "mean"]
        if ratio >= 1.5:
            text += f" That is {ratio:.1f} times the rate."
    bars = [
        Bar(label=str(level)[:40], value=float(row["mean"]), n=int(row["count"]))
        for level, row in table.head(MAX_LEVELS).iterrows()
    ]
    claim: InsightClaim | None
    if len(table) == 2 or frame[column].nunique() == 2:
        claim = InsightClaim(
            claim_type="group_difference",
            variables=[column, t],
            direction="positive",
            reference_group=str(top),
        )
    else:
        claim = InsightClaim(claim_type="group_difference", variables=[column, t])
    return Insight(
        id=f"driver-{column}",
        section="drivers",
        title=f"{column} and {t}",
        text=text,
        importance=importance,
        strength=round(strength, 3),
        columns=[column, t],
        values={"top": str(top), "bottom": str(bottom), "strength": round(strength, 3)},
        chart=BarChart(
            x_label=column,
            y_label=measure,
            value_format="percent" if binary else "number",
            bars=bars,
        ),
        claim=claim,
    )


def _number_driver(
    frame: pd.DataFrame,
    column: str,
    y: pd.Series,
    target: Target,
    strength: float,
    importance: float,
) -> Insight | None:
    x = pd.to_numeric(frame[column], errors="coerce")
    bins = _quartile_bins(x)
    if bins is None:
        return None
    table = (
        pd.DataFrame({"b": bins, "y": y})
        .dropna()
        .groupby("b", observed=True)["y"]
        .agg(["mean", "count"])
    )
    if len(table) < 2:
        return None
    t = target.column
    binary = target.kind == "binary"
    show = _pct if binary else _num
    rho = _rho(x, y)
    direction = "higher" if rho > 0 else "lower"
    outcome = f"a {direction} {t} rate" if binary else f"{direction} {t}"
    # Small tables still get a contrast: a quarter of 25 rows is 6.
    table = table[table["count"] >= min(MIN_LEVEL_ROWS, max(3, len(x.dropna()) // 8))]
    if len(table) < 2:
        return None
    low, high = table.iloc[0], table.iloc[-1]
    low_edge = _num(float(table.index[0].right))
    high_edge = _num(float(table.index[-1].left))
    measure = f"{t} rate" if binary else f"average {t}"
    text = (
        f"Higher {column} goes with {outcome} ({_band(strength)}, Spearman "
        f"rho = {rho:.2f}): {measure} is {show(high['mean'])} in the top quarter of {column} "
        f"(above {high_edge}) against {show(low['mean'])} in the bottom quarter "
        f"(up to {low_edge})."
    )
    bars = [
        Bar(
            label=f"{_num(max(float(b.left), float(x.min())))}-{_num(float(b.right))}",
            value=float(r["mean"]),
            n=int(r["count"]),
        )
        for b, r in table.iterrows()
    ]
    if binary:
        positive = target.positive or "1"
        claim = InsightClaim(
            claim_type="group_difference",
            variables=[t, column],
            direction="positive" if rho > 0 else "negative",
            reference_group=positive,
        )
    else:
        claim = InsightClaim(
            claim_type="correlation",
            variables=[column, t],
            direction="positive" if rho > 0 else "negative",
        )
    return Insight(
        id=f"driver-{column}",
        section="drivers",
        title=f"{column} and {t}",
        text=text,
        importance=importance,
        strength=round(strength, 3),
        columns=[column, t],
        values={
            "rho": round(rho, 3),
            "top_quarter": float(high["mean"]),
            "bottom_quarter": float(low["mean"]),
        },
        chart=BarChart(
            x_label=f"{column} (quarters)",
            y_label=measure,
            value_format="percent" if binary else "number",
            bars=bars,
        ),
        claim=claim,
    )


def _interaction(
    frame: pd.DataFrame, pair: list[str], y: pd.Series, target: Target
) -> Insight | None:
    a, b = pair
    cells = (
        pd.DataFrame({"a": frame[a].astype("string"), "b": frame[b].astype("string"), "y": y})
        .dropna()
        .groupby(["a", "b"], observed=True)["y"]
        .agg(["mean", "count"])
    )
    cells = cells[cells["count"] >= max(20, int(0.02 * len(frame)))].sort_values(
        "mean", ascending=False
    )
    if len(cells) < 3:
        return None
    (ta, tb), (ba, bb) = cells.index[0], cells.index[-1]
    top, bottom = cells.iloc[0], cells.iloc[-1]
    t = target.column
    return Insight(
        id=f"interaction-{a}-{b}",
        section="drivers",
        title=f"{a} and {b} together",
        text=(
            f"Together, {a} and {b} separate {t} more sharply than either alone: "
            f"{_pct(top['mean'])} for {a} = {ta} with {b} = {tb} (n = {int(top['count']):,}) "
            f"against {_pct(bottom['mean'])} for {a} = {ba} with {b} = {bb} "
            f"(n = {int(bottom['count']):,})."
        ),
        importance=86,
        columns=[a, b, t],
        values={"top": float(top["mean"]), "bottom": float(bottom["mean"])},
        chart=BarChart(
            x_label=f"{a} / {b}",
            y_label=f"{t} rate",
            value_format="percent",
            bars=[
                Bar(label=f"{i[0]} / {i[1]}"[:40], value=float(r["mean"]), n=int(r["count"]))
                for i, r in cells.head(MAX_LEVELS).iterrows()
            ],
        ),
    )


# ---- 3. time ---------------------------------------------------------------------------


def _series(frame: pd.DataFrame, keys: pd.Series, column: str) -> pd.Series:
    values = pd.to_numeric(frame[column], errors="coerce")
    grouped = pd.DataFrame({"k": keys, "v": values}).dropna().groupby("k")["v"]
    return (grouped.sum() if is_additive(column) else grouped.mean()).sort_index()


def _time(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: object,
    columns: _Columns,
    entity: str | None,
) -> list[Insight]:
    time_column = getattr(shape, "time_column", None)
    if time_column is None:
        return []
    keys, period = period_keys(frame, time_column, schema)
    out: list[Insight] = []
    measures = [c for c in columns.numeric if c != entity][:3]
    data, note = frame, ""
    if entity is not None:
        # A panel's totals move whenever an entity joins or leaves. Follow only the
        # entities present at both ends, and average them, so growth is like for like.
        years = keys.astype(str).str[:4]
        first, last = years.min(), years.max()
        stayed = set(frame.loc[years == first, entity]) & set(frame.loc[years == last, entity])
        if len(stayed) >= 2:
            mask = frame[entity].isin(stayed)
            data, keys = frame[mask], keys[mask]
            note = f" (average of the {len(stayed)} {entity} values present throughout)"
    for rank, column in enumerate(measures):
        if entity is not None:
            values = pd.to_numeric(data[column], errors="coerce")
            series = pd.DataFrame({"k": keys, "v": values}).dropna().groupby("k")["v"].mean()
            word = "average"
        else:
            series = _series(data, keys, column)
            word = "total" if is_additive(column) else "average"
        if len(series) < 4:
            continue
        found = _growth(series.sort_index(), column, word, period, time_column, rank)
        out.extend(
            item.model_copy(
                update={"text": item.text.replace(f" of {column} ", f" of {column}{note} ", 1)}
            )
            for item in found
        )
        if period == "month" and len(series) >= 24:
            if (season := _seasonality(series, column, rank)) is not None:
                out.append(season)
    return out


def _growth(
    series: pd.Series, column: str, word: str, period: str, time_column: str, rank: int
) -> list[Insight]:
    labels = [str(k) for k in series.index]
    years = pd.Series(series.to_numpy(), index=[label[:4] for label in labels])
    yearly = years.groupby(level=0).agg(["sum" if word == "total" else "mean", "count"])
    full = yearly[yearly["count"] == yearly["count"].max()] if period != "year" else yearly
    first_label, last_label = str(full.index[0]), str(full.index[-1])
    first, last = float(full.iloc[0, 0]), float(full.iloc[-1, 0])
    span = (
        int(last_label) - int(first_label) if first_label.isdigit() and last_label.isdigit() else 0
    )
    rho = _rho(pd.Series(np.arange(len(series)), dtype=float), pd.Series(series.to_numpy()))
    if first == 0 or span <= 0:
        return []
    change = last / first - 1
    yearly_rate = (last / first) ** (1 / span) - 1 if first > 0 and last > 0 else None
    direction = "rose" if change > 0 else "fell"
    steady = abs(rho) >= 0.7
    text = (
        f"The yearly {word} of {column} {direction} from {_num(first)} in {first_label} to "
        f"{_num(last)} in {last_label} ({'+' if change > 0 else ''}{_pct(change)}"
        + (f", about {_pct(yearly_rate)} a year" if yearly_rate is not None else "")
        + ")."
        + (
            f" The movement is steady (rank correlation with time {rho:.2f})."
            if steady
            else f" It does not move in one direction all the way (rank correlation with time {rho:.2f})."
        )
    )
    points = [(label, float(v)) for label, v in zip(labels, series.to_numpy(), strict=True)][-120:]
    return [
        Insight(
            id=f"growth-{column}",
            section="time",
            title=f"{column} over time",
            text=text,
            importance=88 - 3 * rank + (5 if steady else 0),
            strength=round(abs(rho), 3),
            columns=[time_column, column],
            values={"first": first, "last": last, "change": round(change, 4)},
            chart=LineChart(x_label=time_column, y_label=f"{word} {column}", points=points),
            claim=InsightClaim(
                claim_type="trend",
                variables=[time_column, column],
                direction="positive" if rho > 0 else "negative",
            )
            if steady
            else None,
        )
    ]


_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _seasonality(series: pd.Series, column: str, rank: int) -> Insight | None:
    """Each month's level against the 12-month average around it, averaged over years."""
    values = pd.Series(series.to_numpy(), dtype=float)
    centred = values.rolling(12, center=True, min_periods=12).mean()
    ratio = values / centred
    months = pd.Series([int(str(k)[5:7]) for k in series.index])
    index = ratio.groupby(months).mean().dropna()
    if len(index) < 12 or not np.isfinite(index).all():
        return None
    peak, low = int(index.idxmax()), int(index.idxmin())
    up, down = float(index.max() - 1), float(1 - index.min())
    if up < 0.05 and down < 0.05:
        return None
    return Insight(
        id=f"season-{column}",
        section="time",
        title=f"Seasonal pattern in {column}",
        text=(
            f"{column} follows a yearly cycle: {_MONTH_NAMES[peak - 1]} is the peak, about "
            f"{_pct(up)} above the surrounding 12-month average, and {_MONTH_NAMES[low - 1]} "
            f"the low, about {_pct(down)} below it (averaged over every year)."
        ),
        importance=84 - 3 * rank,
        strength=round(up + down, 3),
        columns=[column],
        values={"peak": _MONTH_NAMES[peak - 1], "low": _MONTH_NAMES[low - 1]},
        chart=BarChart(
            x_label="month",
            y_label=f"{column} against its yearly average",
            value_format="percent",
            bars=[Bar(label=_MONTH_NAMES[m - 1], value=float(v - 1)) for m, v in index.items()],
        ),
    )


# ---- 4. comparing entities ------------------------------------------------------------


def _comparison(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: object,
    columns: _Columns,
    entity: str | None,
) -> list[Insight]:
    time_column = getattr(shape, "time_column", None)
    if entity is None or time_column is None:
        return []
    keys, _ = period_keys(frame, time_column, schema)
    latest = keys.dropna().max()
    rows = frame[keys == latest]
    measures = [c for c in columns.numeric if c != entity][:3]
    if rows[entity].nunique() < 3 or not measures:
        return []
    levels = {
        m: pd.to_numeric(rows[m], errors="coerce").groupby(rows[entity]).mean().dropna()
        for m in measures
    }
    out: list[Insight] = []
    for rank, (m, values) in enumerate(levels.items()):
        if len(values) < 3:
            continue
        ordered = values.sort_values(ascending=False)
        out.append(
            Insight(
                id=f"rank-{m}",
                section="comparison",
                title=f"{m} by {entity} in {latest}",
                text=(
                    f"In {latest}, {ordered.index[0]} has the highest {m} ({_num(ordered.iloc[0])}) "
                    f"and {ordered.index[-1]} the lowest ({_num(ordered.iloc[-1])}), "
                    f"{_num(ordered.iloc[0] / ordered.iloc[-1]) if ordered.iloc[-1] else 'n/a'} "
                    f"times as much."
                ),
                importance=70 - 3 * rank,
                columns=[entity, m],
                chart=BarChart(
                    x_label=entity,
                    y_label=m,
                    bars=[Bar(label=str(k)[:40], value=float(v)) for k, v in ordered.items()],
                ),
            )
        )
    # "Highest on one, lowest on another": the comparison an analyst would lead with.
    names = list(levels)
    for i, m1 in enumerate(names):
        for m2 in names[i + 1 :]:
            joined = pd.concat([levels[m1], levels[m2]], axis=1, join="inner").dropna()
            if len(joined) < 3:
                continue
            top1 = joined[m1].idxmax()
            if joined[m2].rank(ascending=True)[top1] == 1:
                across = _rho(joined[m1], joined[m2])
                out.append(
                    Insight(
                        id=f"contrast-{m1}-{m2}",
                        section="comparison",
                        title=f"Highest {m1}, lowest {m2}",
                        text=(
                            f"In {latest}, {top1} has the highest {m1} ({_num(joined.loc[top1, m1])}) "
                            f"but the lowest {m2} ({_num(joined.loc[top1, m2])}) of "
                            f"{len(joined)} {entity} values. Across {entity} values the two "
                            f"have a rank correlation of {across:.2f}, so {top1} is an exception "
                            f"worth explaining."
                        ),
                        importance=87,
                        columns=[entity, m1, m2],
                        values={"entity": str(top1)},
                    )
                )
    return out


# ---- 5. relationships among the other columns -----------------------------------------


def _relationships(
    frame: pd.DataFrame,
    columns: _Columns,
    target: Target | None,
    set_aside: list[str],
    over_time: bool = False,
) -> list[Insight]:
    numeric = [c for c in columns.numeric if target is None or c != target.column]
    pairs: list[tuple[float, str, str]] = []
    for i, a in enumerate(numeric):
        for b in numeric[i + 1 :]:
            rho = _rho(frame[a], frame[b])
            pairs.append((rho, a, b))
    pairs.sort(key=lambda p: -abs(p[0]))
    redundant = [(a, b) for rho, a, b in pairs if abs(rho) >= REDUNDANT]
    if redundant and target is None:  # with an outcome, the drivers already set these aside
        groups: list[set[str]] = []
        for a, b in redundant:
            home = next((g for g in groups if a in g or b in g), None)
            if home is None:
                groups.append({a, b})
            else:
                home |= {a, b}
        for group in groups:
            set_aside.append(
                f"{', '.join(sorted(group))}: near-identical measurements (rank correlation "
                f"0.95 or more); a link between them is expected, not a finding"
            )
    out: list[Insight] = []
    shown = 0
    for rho, a, b in pairs:
        # 0.9 and above between two inputs is expected (two sizes of the same thing).
        ceiling = 0.85 if target else 0.9
        if abs(rho) >= ceiling or abs(rho) < 0.3 or shown >= (1 if target else 4):
            continue
        shown += 1
        out.append(
            Insight(
                id=f"pair-{a}-{b}",
                section="relationships",
                title=f"{a} and {b}",
                text=(
                    f"{a} and {b} move {'together' if rho > 0 else 'in opposite directions'} "
                    f"({_band(abs(rho))}, Spearman rho = {rho:.2f})."
                    + (
                        " Both change over time, so part of this is a shared trend rather "
                        "than a link between them."
                        if over_time
                        else ""
                    )
                ),
                importance=(60 if target else 80) - 4 * shown + 10 * abs(rho),
                strength=round(abs(rho), 3),
                columns=[a, b],
                values={"rho": round(rho, 3)},
                claim=InsightClaim(
                    claim_type="correlation",
                    variables=[a, b],
                    direction="positive" if rho > 0 else "negative",
                ),
            )
        )
    return out


# ---- 6. data quality ------------------------------------------------------------------


def _quality(frame: pd.DataFrame, columns: _Columns) -> list[Insight]:
    out: list[Insight] = []
    missing = frame.isna().mean().sort_values(ascending=False)
    gaps = missing[missing >= 0.05]
    if len(gaps):
        listed = ", ".join(f"{c} {_pct(float(v))}" for c, v in gaps.head(5).items())
        worst = gaps.index[0]
        note = (
            f" {worst} is missing for most rows, so conclusions about it rest on a minority."
            if gaps.iloc[0] > 0.5
            else ""
        )
        out.append(
            Insight(
                id="quality-missing",
                section="quality",
                title="Missing values",
                text=f"Share of rows missing: {listed}.{note}",
                importance=30,
                columns=list(gaps.head(5).index.astype(str)),
            )
        )
    for column in columns.numeric:
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if len(values) < 20 or values.std() == 0:
            continue
        mean, median = float(values.mean()), float(values.median())
        if median > 0 and mean > 1.5 * median:
            top = values.quantile(0.99)
            out.append(
                Insight(
                    id=f"quality-skew-{column}",
                    section="quality",
                    title=f"{column} is skewed",
                    text=(
                        f"{column} is right-skewed: the mean ({_num(mean)}) is well above the "
                        f"median ({_num(median)}), and the top 1% reach {_num(float(top))} or "
                        f"more. Medians describe a typical row better than averages here."
                    ),
                    importance=25,
                    columns=[column],
                )
            )
    return out[:3]


def _questions(insights: list[Insight], target: Target | None) -> list[str]:
    drivers = [i for i in insights if i.section == "drivers" and i.claim is not None]
    questions: list[str] = []
    if target and len(drivers) >= 2:
        a, b = drivers[0].columns[0], drivers[1].columns[0]
        questions.append(
            f"Does {a} still go with {target.column} once {b} is held fixed, or is one "
            f"standing in for the other?"
        )
    if any(i.section == "comparison" and i.id.startswith("contrast") for i in insights):
        questions.append("What sets the exception apart: something this table does not record?")
    if any(i.section == "time" for i in insights):
        questions.append(
            "Is the latest period complete, and did anything change how it was recorded?"
        )
    if target:
        questions.append(
            "These are associations in this table, not causes: which of them could be tested "
            "with an experiment or a natural comparison?"
        )
    return questions[:4]


__all__ = [
    "INSIGHTS_VERSION",
    "Insight",
    "InsightClaim",
    "InsightReport",
    "Target",
    "build_insights",
]
