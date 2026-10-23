"""The Exact tier's analyses (PLAN §5.1): arithmetic only, each figure with its work.

Every analysis is a function `(ctx) -> list[ExactItem]` in `ANALYSES`. The runner calls
the ones the sector pack lists, each on its own, so one that fails becomes a visible
"not run" item and never hides the others. Sentences are rendered here from fixed
templates; no model writes or sees them. Nothing in this module reaches the gateway,
the proposer or memory (D5).
"""

from __future__ import annotations

import calendar
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from pramana.analysis import codebook
from pramana.analysis.computed.config import ComputedConfig, load_computed_config
from pramana.analysis.computed.models import ComputedAnalysis, ExactItem, Scalar
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile
from pramana.analysis.sectors import (
    GENERAL,
    SectorMatch,
    SectorPack,
    detect_sector,
    load_packs,
    pack_for,
)
from pramana.analysis.shape import ShapeProfile, classify_shape, entity_column, period_keys
from pramana.common.logging import get_logger

logger = get_logger(component="computed")

TITLES: dict[str, str] = {
    "period_change": "Change between periods",
    "variance_decomposition": "What accounts for the change",
    "concentration": "Concentration",
    "segment_ranking": "Segments ranked",
    "outliers": "Unusual values",
    "seasonality": "Seasonal pattern",
    "identity": "Columns that restate others",
    "data_quality": "Data quality",
    "prevalence": "Prevalence",
    "weighted_means": "Averages",
    "rates": "Rates per 1,000",
}

_FAILED = "This analysis could not be completed on this table."
_PERIOD_CODE = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}


@dataclass(frozen=True)
class Context:
    frame: pd.DataFrame
    schema: SchemaProfile
    shape: ShapeProfile
    match: SectorMatch
    pack: SectorPack
    config: ComputedConfig
    keys: pd.Series | None
    measures: list[str]
    group: str | None
    weight: str | None

    def column_for(self, role: str) -> str | None:
        return next((c for c, r in self.match.roles.items() if r == role and c in self.frame), None)


# --- helpers ------------------------------------------------------------------------


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _fmt(value: float) -> str:
    text = f"{value:,.2f}"
    return text[:-3] if text.endswith(".00") else text


def _clean(value: object) -> Scalar:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    return None if value is None else str(value)


def _row(**fields: object) -> dict[str, Scalar]:
    return {key: _clean(value) for key, value in fields.items()}


def _label(column: str) -> str:
    known = codebook.lookup(column)
    return f"{known.label.lower()} ({column})" if known else column


def _not_run(kind: str, reason: str, column: str | None = None) -> ExactItem:
    suffix = f":{column}" if column else ""
    return ExactItem(
        id=f"{kind}{suffix}",
        kind=kind,
        status="not_run",
        title=TITLES.get(kind, kind),
        reason=reason,
        columns=[column] if column else [],
    )


def _windows(ctx: Context) -> tuple[list[object], list[object], str, str] | None:
    """(current periods, previous periods, labels): last 12 months vs the 12 before when
    there are two years of months, otherwise the latest period vs the one before."""
    assert ctx.keys is not None
    periods = sorted(set(ctx.keys.dropna().tolist()))
    if len(periods) < 2:
        return None
    if ctx.shape.period == "month" and len(periods) >= 24:
        current, previous = periods[-12:], periods[-24:-12]
        return (
            current,
            previous,
            f"{current[0]} to {current[-1]}",
            f"{previous[0]} to {previous[-1]}",
        )
    return [periods[-1]], [periods[-2]], str(periods[-1]), str(periods[-2])


def _weights(ctx: Context) -> pd.Series | None:
    if ctx.weight is None:
        return None
    return _num(ctx.frame[ctx.weight])


# --- analyses -----------------------------------------------------------------------


def period_change(ctx: Context) -> list[ExactItem]:
    if ctx.keys is None or not ctx.pack.additive_measures:
        return []
    windows = _windows(ctx)
    if windows is None:
        return [_not_run("period_change", "Needs at least two periods to compare.")]
    current, previous, cur_label, prev_label = windows
    time = ctx.shape.time_column or ""
    items = []
    for column in ctx.measures:
        values = _num(ctx.frame[column])
        in_cur = ctx.keys.isin(current) & values.notna()
        in_prev = ctx.keys.isin(previous) & values.notna()
        now, before = float(values[in_cur].sum()), float(values[in_prev].sum())
        change = now - before
        pct = 100.0 * change / before if before != 0 else None
        if change == 0:
            movement = "unchanged from"
        elif pct is None:
            movement = "against"
        else:
            movement = f"{'up' if change > 0 else 'down'} {abs(pct):.1f}% from"
        values_out: dict[str, Scalar] = {
            "current": now,
            "previous": before,
            "change": change,
            "current_label": cur_label,
            "previous_label": prev_label,
        }
        if pct is not None:
            values_out["change_pct"] = pct
        items.append(
            ExactItem(
                id=f"period_change:{column}",
                kind="period_change",
                title=TITLES["period_change"],
                sentence=f"Total {column} was {_fmt(now)} in {cur_label}, {movement} "
                f"{_fmt(before)} in {prev_label}.",
                formula="change = total(current) − total(previous); "
                "change % = change ÷ total(previous) × 100",
                columns=[column, time],
                filters=[f"{time} in {cur_label}", f"{time} in {prev_label}"],
                n_rows=int(in_cur.sum() + in_prev.sum()),
                values=values_out,
            )
        )
    return items


def variance_decomposition(ctx: Context) -> list[ExactItem]:
    if ctx.keys is None or ctx.group is None or not ctx.pack.additive_measures:
        return []
    windows = _windows(ctx)
    if windows is None:
        return []
    current, previous, cur_label, prev_label = windows
    time = ctx.shape.time_column or ""
    items = []
    for column in ctx.measures:
        values = _num(ctx.frame[column])
        segment = ctx.frame[ctx.group].astype(str)
        in_cur = ctx.keys.isin(current) & values.notna()
        in_prev = ctx.keys.isin(previous) & values.notna()
        now = values[in_cur].groupby(segment[in_cur]).sum()
        before = values[in_prev].groupby(segment[in_prev]).sum()
        table = pd.DataFrame({"previous": before, "current": now}).fillna(0.0)
        table["change"] = table["current"] - table["previous"]
        total = float(table["change"].sum())
        if total == 0:
            items.append(
                _not_run(
                    "variance_decomposition",
                    f"Total {column} did not change, so there is no change to split.",
                    column,
                )
            )
            continue
        table["share_of_change"] = table["change"] / total
        table = table.sort_values("change", ascending=total < 0, kind="stable")
        if len(table) > ctx.config.max_segments:
            head = table.iloc[: ctx.config.max_segments - 1]
            rest = table.iloc[ctx.config.max_segments - 1 :].sum()
            table = pd.concat([head, rest.to_frame("other").T])
        top, top_row = str(table.index[0]), table.iloc[0]
        direction = "rise" if total > 0 else "fall"
        items.append(
            ExactItem(
                id=f"variance_decomposition:{column}",
                kind="variance_decomposition",
                title=TITLES["variance_decomposition"],
                sentence=f"{top} accounts for {100 * float(top_row['share_of_change']):.1f}% "
                f"of the {direction} in total {column} between {prev_label} and {cur_label} "
                f"({_fmt(float(top_row['change']))} of {_fmt(total)}).",
                formula="total change = Σ segment change; "
                "share of change = segment change ÷ total change",
                columns=[column, ctx.group, time],
                filters=[f"{time} in {cur_label}", f"{time} in {prev_label}"],
                n_rows=int(in_cur.sum() + in_prev.sum()),
                values={
                    "top_segment": top,
                    "top_share": float(top_row["share_of_change"]),
                    "total_change": total,
                },
                table=[
                    _row(
                        segment=name,
                        previous=r["previous"],
                        current=r["current"],
                        change=r["change"],
                        share_of_change=r["share_of_change"],
                    )
                    for name, r in table.iterrows()
                ],
            )
        )
    return items


def concentration(ctx: Context) -> list[ExactItem]:
    if ctx.group is None or not ctx.pack.additive_measures:
        return []
    items = []
    for column in ctx.measures:
        values = _num(ctx.frame[column])
        valid = values.notna() & ctx.frame[ctx.group].notna()
        totals = values[valid].groupby(ctx.frame.loc[valid, ctx.group].astype(str)).sum()
        totals = totals.sort_values(ascending=False, kind="stable")
        grand = float(totals.sum())
        if grand <= 0 or totals.empty:
            items.append(
                _not_run("concentration", f"Shares of {column} need a positive total.", column)
            )
            continue
        top, share = str(totals.index[0]), float(totals.iloc[0]) / grand
        out: dict[str, Scalar] = {"top_segment": top, "top_share": share, "n_segments": len(totals)}
        extra = ""
        if len(totals) >= 10:
            k = math.ceil(0.1 * len(totals))
            decile = float(totals.iloc[:k].sum()) / grand
            out["top_decile_share"] = decile
            extra = f" The top {k} of {len(totals)} hold {100 * decile:.1f}%."
        items.append(
            ExactItem(
                id=f"concentration:{column}",
                kind="concentration",
                title=TITLES["concentration"],
                sentence=f"{top} holds {100 * share:.1f}% of total {column} "
                f"({_fmt(float(totals.iloc[0]))} of {_fmt(grand)}) "
                f"across {len(totals)} {ctx.group} values.{extra}",
                formula="share = segment total ÷ grand total",
                columns=[column, ctx.group],
                n_rows=int(valid.sum()),
                values=out,
            )
        )
    return items


def segment_ranking(ctx: Context) -> list[ExactItem]:
    if ctx.group is None or not ctx.measures:
        return []
    column = ctx.measures[0]
    values = _num(ctx.frame[column])
    valid = values.notna() & ctx.frame[ctx.group].notna()
    grouped = values[valid].groupby(ctx.frame.loc[valid, ctx.group].astype(str))
    table = pd.DataFrame({"total": grouped.sum(), "mean": grouped.mean(), "n": grouped.size()})
    additive = ctx.pack.additive_measures
    key, word = ("total", "total") if additive else ("mean", "average")
    table = table.sort_values(key, ascending=False, kind="stable")
    grand = float(table["total"].sum())
    table["share"] = table["total"] / grand if additive and grand else np.nan
    shown = table.iloc[: ctx.config.max_segments]
    top, bottom = str(table.index[0]), str(table.index[-1])
    return [
        ExactItem(
            id=f"segment_ranking:{column}",
            kind="segment_ranking",
            title=TITLES["segment_ranking"],
            sentence=f"Ranked by {word} {column}, {top} is highest "
            f"({_fmt(float(table[key].iloc[0]))}) and {bottom} is lowest "
            f"({_fmt(float(table[key].iloc[-1]))}) "
            f"of {len(table)} {ctx.group} values.",
            formula=(
                "total = Σ value per segment; mean = total ÷ rows; share = total ÷ grand total"
                if additive
                else "mean = Σ value per segment ÷ rows in that segment"
            ),
            columns=[column, ctx.group],
            n_rows=int(valid.sum()),
            values={"top_segment": top, "bottom_segment": bottom, "n_segments": len(table)},
            table=[
                _row(
                    segment=name, total=r["total"], mean=r["mean"], n=int(r["n"]), share=r["share"]
                )
                for name, r in shown.iterrows()
            ],
        )
    ]


def outliers(ctx: Context) -> list[ExactItem]:
    cutoff = ctx.config.outlier_robust_z
    items = []
    for column in ctx.measures:
        values = _num(ctx.frame[column])
        if ctx.keys is not None:
            series = values.groupby(ctx.keys).sum(min_count=1).dropna().sort_index()
            unit = f"{ctx.shape.period} totals"
            where = [str(k) for k in series.index]
            n_rows = int((values.notna() & ctx.keys.notna()).sum())
        else:
            series = values.dropna()
            unit = "values"
            where = [f"row {i + 1}" for i in series.index]
            n_rows = len(series)
        if len(series) < 5:
            continue
        x = series.to_numpy(dtype=float)
        median = float(np.median(x))
        scale = 1.4826 * float(np.median(np.abs(x - median)))
        if scale == 0:
            scale = 1.2533 * float(np.mean(np.abs(x - median)))
        if scale == 0:
            continue
        z = (x - median) / scale
        order = [i for i in np.argsort(-np.abs(z), kind="stable") if abs(z[i]) >= cutoff]
        listed = order[: ctx.config.max_outliers_listed]
        if listed:
            first = listed[0]
            sentence = (
                f"{len(order)} of {len(x)} {unit} of {column} sit {cutoff:g} or more robust "
                f"deviations from the median ({_fmt(median)}); the largest is {where[first]} at "
                f"{_fmt(float(x[first]))}."
            )
        else:
            sentence = (
                f"No {unit} of {column} sit {cutoff:g} or more robust deviations from the "
                f"median ({_fmt(median)})."
            )
        items.append(
            ExactItem(
                id=f"outliers:{column}",
                kind="outliers",
                title=TITLES["outliers"],
                sentence=sentence,
                formula="robust z = (x − median) ÷ (1.4826 × median absolute deviation)",
                columns=[column]
                + (
                    [ctx.shape.time_column]
                    if ctx.keys is not None and ctx.shape.time_column
                    else []
                ),
                n_rows=n_rows,
                values={"median": median, "flagged": len(order), "cutoff": cutoff},
                table=[
                    _row(where=where[i], value=float(x[i]), robust_z=float(z[i])) for i in listed
                ],
            )
        )
    return items


def seasonality(ctx: Context) -> list[ExactItem]:
    if ctx.keys is None:
        return []
    period = ctx.shape.period
    if period not in {"month", "quarter"}:
        return [_not_run("seasonality", "A seasonal pattern needs monthly or quarterly periods.")]
    needed = ctx.config.seasonality_min_cycles
    if ctx.shape.full_cycles < needed:
        return [
            _not_run(
                "seasonality",
                f"Needs at least {needed} full years of {period}ly data; this table has "
                f"{ctx.shape.full_cycles}.",
            )
        ]
    length = 12 if period == "month" else 4
    keys = ctx.keys.astype("string")
    years = keys.str[:4]
    complete = keys.groupby(years).nunique()
    complete_years = set(complete[complete >= length].index)
    usable = years.isin(complete_years)
    position = (keys.str[5:7] if period == "month" else keys.str[-1]).astype("Int64")
    items = []
    for column in ctx.measures:
        values = _num(ctx.frame[column])
        mask = usable & values.notna()
        totals = values[mask].groupby([years[mask], position[mask]]).sum()
        means = totals.groupby(level=1).mean()
        overall = float(means.mean())
        if overall == 0:
            continue
        index = means / overall
        peak, low = int(index.idxmax()), int(index.idxmin())

        def name(p: int) -> str:
            return calendar.month_name[p] if period == "month" else f"Q{p}"

        items.append(
            ExactItem(
                id=f"seasonality:{column}",
                kind="seasonality",
                title=TITLES["seasonality"],
                sentence=f"Across {len(complete_years)} full years, {name(peak)} {column} averages "
                f"{float(index[peak]):.2f} times the average {period}; {name(low)} is lowest "
                f"at {float(index[low]):.2f}.",
                formula=f"index = mean total for that {period} of the year "
                f"÷ mean over the {length} {period}s",
                columns=[column, ctx.shape.time_column or ""],
                n_rows=int(mask.sum()),
                values={
                    f"peak_{period}": peak,
                    "peak_index": float(index[peak]),
                    f"low_{period}": low,
                    "low_index": float(index[low]),
                    "years": len(complete_years),
                },
                table=[
                    _row(
                        position=int(p),
                        name=name(int(p)),
                        mean_total=float(means[p]),
                        index=float(index[p]),
                    )
                    for p in means.index
                ],
            )
        )
    return items


def _expected(op: str, a: pd.Series, b: pd.Series) -> pd.Series:
    if op == "difference":
        return a - b
    if op == "sum":
        return a + b
    if op == "product":
        return a * b
    if op == "ratio":
        return a / b.where(b != 0)
    return a / (b / 100.0) ** 2  # bmi: weight kg / (height cm / 100)^2


_EXPRESSION = {
    "difference": "{0} − {1}",
    "sum": "{0} + {1}",
    "product": "{0} × {1}",
    "ratio": "{0} ÷ {1}",
    "bmi": "{0} ÷ ({1} ÷ 100)²",
}


def identity(ctx: Context) -> list[ExactItem]:
    items = []
    for rule in ctx.pack.identities:
        result = ctx.column_for(rule.result)
        inputs = [ctx.column_for(role) for role in rule.inputs]
        if result is None or any(c is None for c in inputs):
            continue
        a, b = (_num(ctx.frame[c]) for c in inputs)  # type: ignore[index]
        r = _num(ctx.frame[result])
        expected = _expected(rule.op, a, b)
        valid = r.notna() & expected.notna()
        n = int(valid.sum())
        if n < ctx.config.identity_min_rows:
            continue
        tol = ctx.config.identity_rel_tolerance
        matches = np.isclose(r[valid], expected[valid], rtol=tol, atol=tol)
        k = int(matches.sum())
        if k / n < ctx.config.identity_min_match:
            continue
        expression = _EXPRESSION[rule.op].format(*inputs)
        items.append(
            ExactItem(
                id=f"identity:{result}",
                kind="identity",
                title=TITLES["identity"],
                sentence=f"{result} equals {expression} on {k} of {n} rows, so it restates those "
                f"columns rather than adding a separate measurement.",
                formula=f"{result} = {expression}, within a relative tolerance of {tol:g}",
                columns=[result, *inputs],  # type: ignore[list-item]
                n_rows=n,
                values={"matching_rows": k, "rows": n},
            )
        )
    return items


def _missing_periods(ctx: Context) -> int:
    if ctx.keys is None or ctx.shape.period not in _PERIOD_CODE:
        return 0
    profile = ctx.schema.columns.get(ctx.shape.time_column or "")
    if profile is None or profile.role is not ColumnRole.DATETIME:
        return 0
    code = _PERIOD_CODE[ctx.shape.period]  # type: ignore[index]
    present = {pd.Period(k, freq=code) for k in ctx.keys.dropna().unique()}
    full = pd.period_range(min(present), max(present), freq=code)
    return len(set(full) - present)


def data_quality(ctx: Context) -> list[ExactItem]:
    frame = ctx.frame
    issues: list[dict[str, Scalar]] = []
    duplicates = int(frame.duplicated().sum())
    if duplicates:
        issues.append(
            _row(
                check="duplicate rows",
                column="",
                count=duplicates,
                detail="identical rows appear more than once",
            )
        )
    for column, role in ctx.match.roles.items():
        if role in ctx.pack.nonnegative and column in frame:
            negative = int((_num(frame[column]) < 0).sum())
            if negative:
                issues.append(
                    _row(
                        check="negative values",
                        column=column,
                        count=negative,
                        detail=f"{role} is expected to be zero or more",
                    )
                )
    for column in frame.columns:
        if frame[column].nunique(dropna=True) == 1:
            issues.append(
                _row(
                    check="constant column",
                    column=column,
                    count=len(frame),
                    detail="one value throughout",
                )
            )
    gaps = _missing_periods(ctx)
    if gaps:
        issues.append(
            _row(
                check="missing periods",
                column=ctx.shape.time_column or "",
                count=gaps,
                detail=f"{ctx.shape.period}s with no rows between the first and last",
            )
        )
    if issues:
        checks = ", ".join(sorted({str(i["check"]) for i in issues}))
        sentence = f"{len(issues)} data-quality issue(s) found: {checks}."
    else:
        sentence = (
            "No issues found by the duplicate-row, negative-value, constant-column and "
            "missing-period checks."
        )
    affected = sorted({str(i["column"]) for i in issues if i["column"]}) or list(
        map(str, frame.columns)
    )
    return [
        ExactItem(
            id="data_quality",
            kind="data_quality",
            title=TITLES["data_quality"],
            sentence=sentence,
            formula="counts of rows or periods failing each check",
            columns=affected,
            n_rows=len(frame),
            values={"issues": len(issues)},
            table=issues,
        )
    ]


_COMPARE: dict[str, Callable[[pd.Series, float], pd.Series]] = {
    ">=": lambda s, v: s >= v,
    ">": lambda s, v: s > v,
    "<=": lambda s, v: s <= v,
    "<": lambda s, v: s < v,
    "==": lambda s, v: s == v,
}


def _share(flag: pd.Series, weights: pd.Series | None) -> float:
    if weights is None:
        return float(flag.mean())
    return float((weights * flag).sum() / weights.sum())


def _code_label(column: str, value: object) -> str:
    known = codebook.lookup(column)
    key = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    return (known.coding or {}).get(key, key) if known else key


def _breakdowns(ctx: Context, valid: pd.Series) -> list[tuple[str, str, pd.Series]]:
    """(by, group label, row mask) for each configured breakdown present in the table."""
    out: list[tuple[str, str, pd.Series]] = []
    for by in ctx.pack.breakdowns:
        column = ctx.column_for(by)
        if column is None:
            continue
        if by == "age" and ctx.pack.age_bands:
            age = _num(ctx.frame[column])
            edges = list(ctx.pack.age_bands)
            for i, low in enumerate(edges):
                high = edges[i + 1] if i + 1 < len(edges) else None
                mask = (age >= low) & (age < high) if high is not None else age >= low
                label = f"age {low:g}–{high - 1:g}" if high is not None else f"age {low:g}+"
                out.append((column, label, valid & mask))
            continue
        for value in sorted(ctx.frame.loc[valid, column].dropna().unique(), key=str):
            out.append((column, _code_label(column, value), valid & (ctx.frame[column] == value)))
    return out


def prevalence(ctx: Context) -> list[ExactItem]:
    weights = _weights(ctx)
    items = []
    for rule in ctx.pack.prevalence:
        column = ctx.column_for(rule.role)
        if column is None:
            continue
        values = _num(ctx.frame[column])
        valid = values.notna()
        if weights is not None:
            valid &= weights.notna() & (weights > 0)
        n = int(valid.sum())
        if n < ctx.config.min_prevalence_rows:
            items.append(
                _not_run(
                    "prevalence",
                    f"Needs at least {ctx.config.min_prevalence_rows} "
                    f"rows with a value of {column}.",
                    column,
                )
            )
            continue
        flag = _COMPARE[rule.op](values, rule.value).astype(float)
        w = weights[valid] if weights is not None else None
        share = _share(flag[valid], w)
        condition = f"{column} {rule.op} {rule.value:g}"
        if weights is not None:
            sentence = (
                f"{100 * share:.1f}% of respondents have {rule.label} ({condition}), "
                f"weighted by {ctx.weight} (n = {n})."
            )
            formula = "share = Σ weight × [condition] ÷ Σ weight"
        else:
            sentence = (
                f"{100 * share:.1f}% of this sample has {rule.label} ({condition}; n = {n}). "
                f"This is a share of this sample, not a population estimate."
            )
            formula = "share = rows meeting the condition ÷ rows with a value"
        table = []
        used = [column]
        for by, label, mask in _breakdowns(ctx, valid):
            if by not in used:
                used.append(by)
            rows = int(mask.sum())
            if rows < ctx.config.min_group_rows:
                continue
            table.append(
                _row(
                    by=by,
                    group=label,
                    n=rows,
                    share=_share(flag[mask], weights[mask] if weights is not None else None),
                )
            )
        if weights is not None:
            used.append(ctx.weight)  # type: ignore[arg-type]
        items.append(
            ExactItem(
                id=f"prevalence:{column}",
                kind="prevalence",
                title=TITLES["prevalence"],
                sentence=sentence,
                formula=formula,
                columns=used,
                filters=[condition],
                n_rows=n,
                values={
                    "share": share,
                    "n": n,
                    "cases": int(flag[valid].sum()),
                    "weighted": weights is not None,
                    "threshold": rule.value,
                },
                table=table,
            )
        )
    return items


def weighted_means(ctx: Context) -> list[ExactItem]:
    weights = _weights(ctx)
    items = []
    for column in ctx.measures:
        values = _num(ctx.frame[column])
        valid = values.notna()
        if weights is not None:
            valid &= weights.notna() & (weights > 0)
        n = int(valid.sum())
        if n == 0:
            continue
        known = codebook.lookup(column)
        unit = f" {known.unit}" if known and known.unit else ""
        if weights is not None:
            mean = float(np.average(values[valid], weights=weights[valid]))
            sentence = (
                f"Average {_label(column)} is {_fmt(mean)}{unit}, "
                f"weighted by {ctx.weight} (n = {n})."
            )
            formula = "mean = Σ weight × value ÷ Σ weight"
        else:
            mean = float(values[valid].mean())
            sentence = (
                f"Average {_label(column)} in this sample is {_fmt(mean)}{unit} (n = {n}); "
                f"not a population estimate."
            )
            formula = "mean = Σ value ÷ rows with a value"
        items.append(
            ExactItem(
                id=f"weighted_means:{column}",
                kind="weighted_means",
                title=TITLES["weighted_means"],
                sentence=sentence,
                formula=formula,
                columns=[column] + ([ctx.weight] if weights is not None else []),  # type: ignore[list-item]
                n_rows=n,
                values={"mean": mean, "n": n, "weighted": weights is not None},
            )
        )
    return items


def rates(ctx: Context) -> list[ExactItem]:
    cases, population = ctx.column_for("cases"), ctx.column_for("population")
    if cases is None or population is None:
        return []
    c, p = _num(ctx.frame[cases]), _num(ctx.frame[population])
    valid = c.notna() & p.notna() & (p > 0)
    if not valid.any():
        return []
    rate = 1000.0 * float(c[valid].sum()) / float(p[valid].sum())
    table = []
    if ctx.group is not None:
        grouped = pd.DataFrame(
            {"c": c[valid], "p": p[valid], "g": ctx.frame.loc[valid, ctx.group].astype(str)}
        )
        sums = grouped.groupby("g")[["c", "p"]].sum()
        sums["rate"] = 1000.0 * sums["c"] / sums["p"]
        sums = sums.sort_values("rate", ascending=False, kind="stable").iloc[
            : ctx.config.max_segments
        ]
        table = [
            _row(segment=name, cases=r["c"], population=r["p"], rate_per_1000=r["rate"])
            for name, r in sums.iterrows()
        ]
    return [
        ExactItem(
            id=f"rates:{cases}",
            kind="rates",
            title=TITLES["rates"],
            sentence=f"There are {rate:.2f} {cases} per 1,000 {population} "
            f"across {int(valid.sum())} rows.",
            formula=f"rate = Σ {cases} ÷ Σ {population} × 1,000",
            columns=[cases, population] + ([ctx.group] if ctx.group else []),
            n_rows=int(valid.sum()),
            values={"rate_per_1000": rate},
            table=table,
        )
    ]


ANALYSES: dict[str, Callable[[Context], list[ExactItem]]] = {
    "period_change": period_change,
    "variance_decomposition": variance_decomposition,
    "concentration": concentration,
    "segment_ranking": segment_ranking,
    "outliers": outliers,
    "seasonality": seasonality,
    "identity": identity,
    "data_quality": data_quality,
    "prevalence": prevalence,
    "weighted_means": weighted_means,
    "rates": rates,
}


# --- runner -------------------------------------------------------------------------


def _measures(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    match: SectorMatch,
    pack: SectorPack,
    exclude: set[str],
    limit: int,
) -> list[str]:
    numeric = [
        name
        for name, profile in schema.columns.items()
        if profile.role is ColumnRole.NUMERIC
        and profile.usable_for_hypotheses
        and name not in exclude
        and name in frame
    ]
    if pack is not GENERAL:
        chosen = [
            c
            for c in frame.columns
            if match.roles.get(c) in set(pack.measures)
            and c not in exclude
            and _num(frame[c]).notna().any()
        ]
        if chosen:
            return chosen[:limit]
    return numeric[:limit]


def compute_analysis(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    *,
    config: ComputedConfig | None = None,
    packs: Mapping[str, SectorPack] | None = None,
    sector: str | None = None,
) -> ComputedAnalysis:
    """Run the Exact tier on a cleaned table.

    Guarantees: deterministic for the same inputs; every analysis the pack lists runs
    independently, and one that raises becomes a "not run" item with a fixed message
    (the exception text is logged, never shown); nothing here calls a model.
    """
    config = config or load_computed_config()
    packs = load_packs() if packs is None else packs
    match = detect_sector(list(map(str, frame.columns)), packs, override=sector)
    pack = pack_for(match, packs)
    shape = classify_shape(frame, schema, match.roles)
    keys = None
    if shape.time_column is not None:
        keys, _ = period_keys(frame, shape.time_column, schema)
    weight = next((c for c, r in match.roles.items() if r == "survey_weight" and c in frame), None)
    group = shape.entity_column or entity_column(
        frame, schema, match.roles, exclude=shape.time_column
    )
    exclude = {c for c in (shape.time_column, weight, group) if c}
    exclude |= {c for c, p in schema.columns.items() if p.role is ColumnRole.ID_LIKE}
    ctx = Context(
        frame=frame,
        schema=schema,
        shape=shape,
        match=match,
        pack=pack,
        config=config,
        keys=keys,
        measures=_measures(frame, schema, match, pack, exclude, config.max_measures),
        group=group,
        weight=weight,
    )
    items: list[ExactItem] = []
    for name in pack.analyses:
        analysis = ANALYSES.get(name)
        if analysis is None:
            items.append(_not_run(name, "This analysis is not available."))
            continue
        try:
            items.extend(analysis(ctx))
        except Exception:
            logger.exception("computed_analysis_failed", analysis=name)
            items.append(_not_run(name, _FAILED))
    return ComputedAnalysis(
        sector=match, shape=shape, scope_note=pack.wording.scope_note, items=items
    )
