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
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from pramana.analysis import codebook
from pramana.analysis.computed.charts import (
    Bar,
    BarChart,
    HeatCell,
    HeatStrip,
    LineChart,
    ParetoBar,
    ParetoChart,
    WaterfallChart,
    WaterfallStep,
)
from pramana.analysis.computed.config import ComputedConfig, load_computed_config
from pramana.analysis.computed.models import COMPUTED_VERSION, ComputedAnalysis, ExactItem, Scalar
from pramana.analysis.computed.story import build_story
from pramana.analysis.computed.summary import template_summary
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile, parse_timestamps
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
    "margins": "Margins",
    "variance_decomposition": "What accounts for the change",
    "concentration": "Concentration",
    "segment_ranking": "Segments ranked",
    "outliers": "Unusual values",
    "seasonality": "Seasonal pattern",
    "price_volume_mix": "Price, volume and mix",
    "segment_growth": "Growth by segment",
    "customer_view": "Customers",
    "rfm": "Customer groups (recency, frequency, money)",
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


MISSING_SEGMENT = "(missing)"


def _num(series: pd.Series) -> pd.Series:
    """Numbers only; text and ±inf become missing, so no sum or share can be infinite."""
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _segments(ctx: Context) -> pd.Series:
    """The group label per row; a blank group is its own segment, never dropped, so the
    segments always add up to the same total as the period change."""
    assert ctx.group is not None
    return ctx.frame[ctx.group].astype("string").fillna(MISSING_SEGMENT)


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


_FISCAL_NAME = re.compile(r"fiscal|financial|(?:^|[^a-z])fy(?:[^a-z]|$)")


def _fiscal_names(
    ctx: Context, current: list[object], previous: list[object]
) -> tuple[str, str] | None:
    """Names for two windows from the table's own fiscal-year column, when each window is
    exactly one of its labels (so "FY2025" is said only when the rows say it)."""
    assert ctx.keys is not None
    column = next(
        (
            c
            for c in ctx.frame.columns
            if _FISCAL_NAME.search(str(c).lower()) and c != ctx.shape.time_column
        ),
        None,
    )
    if column is None:
        return None
    names = []
    for window in (current, previous):
        labels = ctx.frame.loc[ctx.keys.isin(window), column].dropna().astype(str).unique()
        if len(labels) != 1:
            return None
        label = labels[0].strip()
        names.append(f"fiscal year {label}" if label.isdigit() else label)
    if names[0] == names[1]:
        return None
    return (
        f"{names[0]} ({current[0]} to {current[-1]})",
        f"{names[1]} ({previous[0]} to {previous[-1]})",
    )


def _windows(ctx: Context) -> tuple[list[object], list[object], str, str] | None:
    """(current periods, previous periods, labels): last 12 months vs the 12 before when
    there are two years of months, otherwise the latest period vs the one before."""
    assert ctx.keys is not None
    periods = sorted(set(ctx.keys.dropna().tolist()))
    if len(periods) < 2:
        return None
    if ctx.shape.period == "month" and len(periods) >= 24:
        # Calendar months back from the last one, and only if every one of them is there:
        # 24 distinct keys with a gap would compare two windows of different lengths.
        last = pd.Period(str(periods[-1]), freq="M")
        months = [str(p) for p in pd.period_range(last - 23, last, freq="M")]
        if set(months) <= set(map(str, periods)):
            current, previous = months[12:], months[:12]
            fiscal = _fiscal_names(ctx, current, previous)
            if fiscal is not None:
                return current, previous, fiscal[0], fiscal[1]
            return (
                current,
                previous,
                f"the 12 months to {current[-1]}",
                f"the 12 months to {previous[-1]}",
            )
    return [periods[-1]], [periods[-2]], str(periods[-1]), str(periods[-2])


def _weights(ctx: Context) -> pd.Series | None:
    if ctx.weight is None:
        return None
    return _num(ctx.frame[ctx.weight])


def _period_totals(ctx: Context, values: pd.Series) -> pd.Series:
    assert ctx.keys is not None
    return values.groupby(ctx.keys).sum(min_count=1).dropna().sort_index()


def _line(ctx: Context, column: str, totals: pd.Series, marks: Sequence[str] = ()) -> LineChart:
    """Period totals as a line, the most recent `max_chart_points` periods."""
    shown = totals.iloc[-ctx.config.max_chart_points :]
    return LineChart(
        x_label=ctx.shape.time_column or "period",
        y_label=f"total {column}",
        points=[(str(k), float(v)) for k, v in shown.items()],
        marks=[m for m in marks if m in set(map(str, shown.index))],
    )


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
        # A percentage of a zero or negative base reads backwards ("up" while the ratio is
        # negative), so it is only given against a positive one.
        pct = 100.0 * change / before if before > 0 else None
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
                chart=_line(ctx, column, _period_totals(ctx, values)),
            )
        )
    return items


def _pick(ctx: Context, role: str, preferred: str) -> str | None:
    """The column of `role` named like `preferred` (a regex), else the first of that role."""
    columns = [c for c, r in ctx.match.roles.items() if r == role and c in ctx.frame]
    return next((c for c in columns if re.search(preferred, str(c).lower())), None) or (
        columns[0] if columns else None
    )


def _margin(
    revenue: pd.Series, cost: pd.Series, mask: pd.Series
) -> tuple[float, float, float] | None:
    """(margin %, revenue, cost) over the rows in `mask`, or None without positive revenue."""
    both = revenue.notna() & cost.notna() & mask
    rev, cst = float(revenue[both].sum()), float(cost[both].sum())
    if rev <= 0:
        return None
    return 100.0 * (rev - cst) / rev, rev, cst


def margins(ctx: Context) -> list[ExactItem]:
    """Margin (revenue less cost, as a share of revenue) now against before, with the
    segments whose margin moved most. Arithmetic on the table; no model."""
    amount = _pick(ctx, "amount", r"revenue|sales|turnover|income")
    cost = _pick(ctx, "cost", r"cost|cogs|expense")
    if ctx.keys is None or amount is None or cost is None or not ctx.pack.additive_measures:
        return []
    windows = _windows(ctx)
    if windows is None:
        return [_not_run("margins", "Needs at least two periods to compare.")]
    current, previous, cur_label, prev_label = windows
    revenue, spend = _num(ctx.frame[amount]), _num(ctx.frame[cost])
    now = _margin(revenue, spend, ctx.keys.isin(current))
    before = _margin(revenue, spend, ctx.keys.isin(previous))
    if now is None or before is None:
        return [_not_run("margins", f"Margin needs positive total {amount} in both periods.")]
    (m1, r1, c1), (m0, r0, c0) = now, before
    delta = m1 - m0
    movement = (
        f"unchanged from {m0:.1f}%"
        if abs(delta) < 0.05
        else f"{'up' if delta > 0 else 'down'} {abs(delta):.1f} points from {m0:.1f}%"
    )
    sentence = (
        f"Margin ({amount} less {cost}, as a share of {amount}) was {m1:.1f}% in "
        f"{cur_label}, {movement} in {prev_label}"
    )
    if r0 > 0 and c0 > 0:
        r_pct, c_pct = 100.0 * (r1 - r0) / r0, 100.0 * (c1 - c0) / c0
        sentence += (
            f"; {amount} {'rose' if r_pct >= 0 else 'fell'} {abs(r_pct):.1f}% "
            f"while {cost} {'rose' if c_pct >= 0 else 'fell'} {abs(c_pct):.1f}%"
        )
    rows: list[dict[str, Scalar]] = []
    fiscal = next((c for c in ctx.frame.columns if _FISCAL_NAME.search(str(c).lower())), None)
    others = [
        c
        for c, p in ctx.schema.columns.items()
        if p.role is ColumnRole.CATEGORICAL
        and c in ctx.frame
        and c not in (ctx.group, ctx.shape.time_column, fiscal)
        and 2 <= ctx.frame[c].nunique() <= ctx.config.max_margin_levels
    ]
    for column in ([ctx.group] if ctx.group else []) + others[: ctx.config.max_margin_columns]:
        level = ctx.frame[column].astype("string").fillna(MISSING_SEGMENT)
        for value in sorted(level.unique()):
            in_level = level == value
            a = _margin(revenue, spend, ctx.keys.isin(current) & in_level)
            b = _margin(revenue, spend, ctx.keys.isin(previous) & in_level)
            if a is None or b is None:
                continue
            rows.append(
                _row(
                    column=column,
                    level=value,
                    margin_now_pct=a[0],
                    margin_before_pct=b[0],
                    change_points=a[0] - b[0],
                    revenue_now=a[1],
                )
            )
    rows.sort(key=lambda r: float(r["change_points"] or 0.0))
    if rows and float(rows[0]["change_points"] or 0.0) <= -0.05:
        worst = rows[0]
        sentence += (
            f". The largest fall is {worst['column']} = {worst['level']}, from "
            f"{float(worst['margin_before_pct'] or 0):.1f}% to "
            f"{float(worst['margin_now_pct'] or 0):.1f}% "
            f"({abs(float(worst['change_points'] or 0)):.1f} points)"
        )
    per_cost = spend.groupby(ctx.keys).sum(min_count=1)
    per_rev = revenue.groupby(ctx.keys).sum(min_count=1)
    series = (100.0 * (per_rev - per_cost) / per_rev.where(per_rev > 0)).dropna().sort_index()
    shown = series.iloc[-ctx.config.max_chart_points :]
    time = ctx.shape.time_column or "period"
    return [
        ExactItem(
            id=f"margins:{amount}:{cost}",
            kind="margins",
            title=TITLES["margins"],
            sentence=sentence + ".",
            formula="margin % = (total revenue − total cost) ÷ total revenue × 100; "
            "change in points = margin(current) − margin(previous)",
            columns=[amount, cost, time],
            filters=[f"{time} in {cur_label}", f"{time} in {prev_label}"],
            n_rows=int(ctx.keys.isin(current + previous).sum()),
            values={"margin_now_pct": m1, "margin_before_pct": m0, "change_points": delta},
            table=rows[: ctx.config.max_outliers_listed],
            chart=LineChart(
                x_label=time,
                y_label="margin %",
                points=[(str(k), float(v)) for k, v in shown.items()],
            ),
        )
    ]


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
        segment = _segments(ctx)
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
        top_change, share = float(top_row["change"]), float(top_row["share_of_change"])
        if share <= 1:
            sentence = (
                f"{top} accounts for {100 * share:.1f}% of the {direction} in total {column} "
                f"from {prev_label} to {cur_label} ({_fmt(top_change)} of {_fmt(total)})."
            )
        else:
            # One segment moved more than the total: the others moved the opposite way.
            def moved(x: float) -> str:
                return f"{'rose' if x > 0 else 'fell'} by {_fmt(abs(x))}"

            sentence = (
                f"From {prev_label} to {cur_label}, {top} {moved(top_change)} while total "
                f"{column} {moved(total)}; the other {ctx.group} values together "
                f"{moved(total - top_change)}."
            )
        items.append(
            ExactItem(
                id=f"variance_decomposition:{column}",
                kind="variance_decomposition",
                title=TITLES["variance_decomposition"],
                sentence=sentence,
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
                chart=WaterfallChart(
                    y_label=f"total {column}",
                    # short axis labels: the last period of each window
                    start_label=f"to {previous[-1]}" if len(previous) > 1 else prev_label,
                    end_label=f"to {current[-1]}" if len(current) > 1 else cur_label,
                    start=float(table["previous"].sum()),
                    end=float(table["current"].sum()),
                    steps=[
                        WaterfallStep(label=str(name), value=float(r["change"]))
                        for name, r in table.iterrows()
                    ],
                ),
            )
        )
    return items


def concentration(ctx: Context) -> list[ExactItem]:
    if ctx.group is None or not ctx.pack.additive_measures:
        return []
    items = []
    for column in ctx.measures:
        values = _num(ctx.frame[column])
        valid = values.notna()
        totals = values[valid].groupby(_segments(ctx)[valid]).sum()
        totals = totals.sort_values(ascending=False, kind="stable")
        grand = float(totals.sum())
        if totals.empty or grand <= 0 or bool((totals < 0).any()):
            # A share of a total that some segments subtract from can exceed 100%.
            items.append(
                _not_run(
                    "concentration",
                    f"Shares of {column} are not given when a segment total is below zero.",
                    column,
                )
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
                chart=_pareto(ctx, column, totals, grand),
            )
        )
    return items


def _pareto(ctx: Context, column: str, totals: pd.Series, grand: float) -> ParetoChart:
    """Segments largest first with the running share; the tail is grouped as "other"."""
    keep = ctx.config.max_segments - 1
    head = totals.iloc[:keep] if len(totals) > ctx.config.max_segments else totals
    bars = [(str(k), float(v)) for k, v in head.items()]
    if len(head) < len(totals):
        bars.append(("other", float(totals.iloc[keep:].sum())))
    running, out = 0.0, []
    for label, value in bars:
        running += value
        out.append(ParetoBar(label=label, value=value, cumulative_share=running / grand))
    return ParetoChart(y_label=f"total {column}", bars=out)


def segment_ranking(ctx: Context) -> list[ExactItem]:
    if ctx.group is None or not ctx.measures:
        return []
    column = ctx.measures[0]
    values = _num(ctx.frame[column])
    valid = values.notna()
    if not valid.any():
        return []
    grouped = values[valid].groupby(_segments(ctx)[valid])
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
            chart=BarChart(
                x_label=ctx.group,
                y_label=f"{word} {column}",
                bars=[
                    Bar(label=str(name), value=float(r[key]), n=int(r["n"]))
                    for name, r in shown.iterrows()
                ],
            ),
        )
    ]


def _ratio_reads_well(value: float, median: float, raw_median: float) -> bool:
    """A "times the median" ratio only where the segment's own median is positive and the
    ratio does not round to zero; otherwise it reads as nonsense ("0.0 times")."""
    return bool(raw_median > 0 and median > 0 and round(value / median, 1) > 0)


def _against_median(value: float, median: float, raw_median: float, basis: str, z: float) -> str:
    """The clause that places a flagged row against its segment: a ratio when one reads
    well, robust deviations alone (never a ratio) when the median is not positive."""
    if _ratio_reads_well(value, median, raw_median):
        return f"{value / median:.1f} times {basis}."
    if raw_median <= 0:
        basis = basis.replace("median", "typical non-zero value")
    return f"{abs(z):.1f} robust deviations {'above' if z > 0 else 'below'} {basis}."


def _row_outliers(ctx: Context, column: str, values: pd.Series) -> ExactItem | None:
    """Single rows far from their segment's usual size (robust z of log(value / segment
    median)). Needed where several rows share a period: period totals hide one bad row."""
    assert ctx.keys is not None
    positive = values.where(values > 0)
    if int(positive.notna().sum()) < 5:
        return None
    segment = _segments(ctx) if ctx.group else pd.Series("all", index=values.index)
    median = positive.groupby(segment).transform("median")
    raw_median = values.groupby(segment).transform("median")
    ratio = np.log(positive / median).replace([np.inf, -np.inf], np.nan).dropna()
    x = ratio.to_numpy(dtype=float)
    centre = float(np.median(x))
    scale = 1.4826 * float(np.median(np.abs(x - centre)))
    if scale == 0:
        return None
    z = (x - centre) / scale
    cutoff = ctx.config.outlier_robust_z
    order = [i for i in np.argsort(-np.abs(z), kind="stable") if abs(z[i]) >= cutoff]
    basis = f"their {ctx.group} median" if ctx.group else "the column median"
    if not order:
        sentence = (
            f"No single row of {column} sits {cutoff:g} or more robust deviations from {basis}."
        )
    else:
        top = ratio.index[order[0]]
        sentence = (
            f"{len(order)} of {len(x)} rows of {column} sit {cutoff:g} or more robust deviations "
            f"from {basis}; the largest is row {int(top) + 1} ({ctx.keys[top]}) at "
            f"{_fmt(float(positive[top]))}, {_against_median(float(positive[top]), median[top], raw_median[top], basis, float(z[order[0]]))}"
        )
    listed = order[: ctx.config.max_outliers_listed]
    return ExactItem(
        id=f"row_outliers:{column}",
        kind="outliers",
        title=TITLES["outliers"],
        sentence=sentence,
        formula="robust z of ln(value / segment median) = (r - median r) / (1.4826 x MAD of r)",
        columns=[column] + ([ctx.group] if ctx.group else []),
        n_rows=len(x),
        values={"flagged": len(order), "cutoff": cutoff},
        table=[
            _row(
                where=f"row {int(ratio.index[i]) + 1} ({ctx.keys[ratio.index[i]]})",
                value=float(positive[ratio.index[i]]),
                times_median=(
                    float(positive[ratio.index[i]] / median[ratio.index[i]])
                    if _ratio_reads_well(
                        float(positive[ratio.index[i]]),
                        median[ratio.index[i]],
                        raw_median[ratio.index[i]],
                    )
                    else None
                ),
                robust_z=float(z[i]),
            )
            for i in listed
        ],
    )


def outliers(ctx: Context) -> list[ExactItem]:
    cutoff = ctx.config.outlier_robust_z
    items = []
    row_items = []
    for column in ctx.measures:
        values = _num(ctx.frame[column])
        if ctx.keys is not None and bool(ctx.keys.duplicated().any()):
            row_item = _row_outliers(ctx, column, values)
            if row_item is not None:
                row_items.append(row_item)
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
                chart=(
                    _line(ctx, column, series, [where[i] for i in order])
                    if ctx.keys is not None
                    else None
                ),
            )
        )
    return items + row_items


def _consecutive_tail(keys: pd.Series, period: str) -> list[pd.Period]:
    """The longest run of consecutive periods that ends at the table's last period."""
    freq = _PERIOD_CODE[period]
    present = sorted({pd.Period(str(k), freq=freq) for k in keys.dropna().unique()})
    run = [present[-1]]
    for p in reversed(present[:-1]):
        if p + 1 != run[0]:
            break
        run.insert(0, p)
    return run


def _rolling_seasonality(ctx: Context, period: str, length: int, needed: int) -> list[ExactItem]:
    """Seasonal indices from any `needed` or more cycles of consecutive periods.

    Index = value ÷ centred moving average of one cycle, averaged per position in the
    year and scaled to mean 1. The moving average follows growth, so a rising series does
    not make its late months look seasonal. With 2 cycles each position is seen once;
    the sentence says how many times.
    """
    run = _consecutive_tail(ctx.keys, period)
    if len(run) < needed * length:
        return [
            _not_run(
                "seasonality",
                f"Needs at least {needed} full years of {period}ly data ({needed * length} "
                f"consecutive {period}s ending at the latest one); this table has {len(run)}.",
            )
        ]
    index = [str(p) for p in run]
    keys = ctx.keys.astype("string")
    items = []
    for column in ctx.measures:
        values = _num(ctx.frame[column])
        mask = keys.isin(index) & values.notna()
        totals = values[mask].groupby(keys[mask]).sum().reindex(index)
        if totals.isna().any() or (totals <= 0).any():
            items.append(
                _not_run(
                    "seasonality",
                    f"A seasonal index needs a positive total {column} in every {period}.",
                    column,
                )
            )
            continue
        x = totals.to_numpy(dtype=float)
        trailing = pd.Series(x).rolling(length).mean().to_numpy()
        half = length // 2
        # centred 2 x length average, for an even cycle length: the mean of the two
        # trailing averages that straddle each period
        centred = np.full_like(x, np.nan)
        centred[half : len(x) - half] = (trailing[length - 1 : len(x) - 1] + trailing[length:]) / 2
        ratio = x / centred
        position = np.array([p.month if period == "month" else p.quarter for p in run])
        ok = ~np.isnan(ratio)
        by_position = pd.Series(ratio[ok]).groupby(position[ok]).mean()
        if len(by_position) < length:
            items.append(
                _not_run("seasonality", f"Too few {period}s to place every position.", column)
            )
            continue
        idx = by_position / by_position.mean()
        counts = pd.Series(position[ok]).value_counts()
        seen = int(counts.min())
        peak, low = int(idx.idxmax()), int(idx.idxmin())

        def name(p: int) -> str:
            return calendar.month_name[p] if period == "month" else f"Q{p}"

        items.append(
            ExactItem(
                id=f"seasonality:{column}",
                kind="seasonality",
                title=TITLES["seasonality"],
                sentence=f"Over the last {len(run)} {period}s ({run[0]} to {run[-1]}), "
                f"{name(peak)} "
                f"{column} runs {float(idx[peak]):.2f} times the usual level for the year; "
                f"{name(low)} is lowest at {float(idx[low]):.2f}. Each {period} was seen "
                f"{seen} time{'s' if seen != 1 else ''}.",
                formula=f"index = {period} total ÷ centred moving average of {length} {period}s, "
                f"averaged per {period} of the year and scaled to mean 1",
                columns=[column, ctx.shape.time_column or ""],
                n_rows=int(mask.sum()),
                values={
                    f"peak_{period}": peak,
                    "peak_index": float(idx[peak]),
                    f"low_{period}": low,
                    "low_index": float(idx[low]),
                    "periods": len(run),
                    "times_seen": seen,
                    "years": len(run) // length,
                },
                table=[
                    _row(position=int(p), name=name(int(p)), index=float(idx[p])) for p in idx.index
                ],
                chart=HeatStrip(
                    label=column,
                    cells=[HeatCell(label=name(int(p)), index=float(idx[p])) for p in idx.index],
                ),
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
    length = 12 if period == "month" else 4
    calendar_years = ctx.shape.full_cycles >= needed
    if not calendar_years:
        # Fewer than two calendar years do not mean fewer than two years of data: a
        # financial year runs April to March. Use any run of consecutive periods instead.
        return _rolling_seasonality(ctx, period, length, needed)
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
        if overall <= 0:
            # An index against a negative average flips: the worst month would read as the
            # peak. Seasonality is only described for a positive average.
            items.append(
                _not_run(
                    "seasonality",
                    f"A seasonal index needs a positive average {column}.",
                    column,
                )
            )
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
                chart=HeatStrip(
                    label=column,
                    cells=[
                        HeatCell(label=name(int(p)), index=float(index[p])) for p in means.index
                    ],
                ),
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


_PARTIAL_PERIOD_NOTE = (
    "The last {period} ({label}) looks incomplete ({why}); figures involving it should be "
    "read with care."
)
_PARTIAL_KINDS = {
    "period_change",
    "seasonality",
    "variance_decomposition",
    "segment_growth",
    "trend",
}


def _incomplete_last_period(ctx: Context) -> tuple[str, str] | None:
    """(last period label, reason) when the table's last period looks only partly filled.

    Judged from the table's own data, never a calendar guess: the last period has far
    fewer rows than the median earlier period, or (monthly and daily tables) its last date
    falls well short of the day reached in a typical earlier period. Tables stamped on one
    fixed day of the month are therefore never flagged by the date test.
    """
    if ctx.keys is None or ctx.shape.period not in _PERIOD_CODE:
        return None
    keys = ctx.keys.dropna()
    counts = keys.value_counts().sort_index()
    if len(counts) < 4:
        return None
    last = counts.index[-1]
    typical = float(counts.iloc[:-1].median())
    if typical >= 4 and float(counts.iloc[-1]) < 0.5 * typical:
        return str(last), (
            f"{int(counts.iloc[-1])} rows against a typical {typical:g} per {ctx.shape.period}"
        )
    profile = ctx.schema.columns.get(ctx.shape.time_column or "")
    if (
        ctx.shape.period == "month"
        and profile is not None
        and profile.role is ColumnRole.DATETIME
        and ctx.shape.time_column in ctx.frame
    ):
        stamps = parse_timestamps(ctx.frame[ctx.shape.time_column])
        days = stamps.dt.day.reindex(keys.index)
        reach = days.groupby(keys).max().sort_index()
        usual = float(reach.iloc[:-1].median())
        if usual > 1 and float(reach.iloc[-1]) < 0.7 * usual:
            return str(last), (
                f"its data stops on day {int(reach.iloc[-1])} of the month, where earlier "
                f"months reach day {usual:g}"
            )
    return None


def _flag_incomplete_last_period(
    ctx: Context, items: list[ExactItem]
) -> list[ExactItem]:
    """Append the incomplete-period caveat to every figure that involves the last period.
    Nothing is dropped or recomputed."""
    found = _incomplete_last_period(ctx)
    if found is None:
        return items
    label, why = found
    note = _PARTIAL_PERIOD_NOTE.format(period=ctx.shape.period, label=label, why=why)
    return [
        item.model_copy(update={"sentence": f"{item.sentence} {note}"})
        if item.kind in _PARTIAL_KINDS and item.status == "ok"
        else item
        for item in items
    ]


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
    partial = _incomplete_last_period(ctx)
    if partial is not None:
        issues.append(
            _row(
                check="incomplete last period",
                column=ctx.shape.time_column or "",
                count=1,
                detail=f"{partial[0]} looks incomplete ({partial[1]}); read figures involving it with care",
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


#: Codebook labels that record a non-answer rather than a measurement.
_NON_ANSWER_LABELS = frozenset({"refused", "don't know"})


def _non_answers(column: str) -> list[float]:
    """Codes that mean "Refused" or "Don't know" for a codebook column. They leave the
    denominator of a share entirely: counting them as "no" understates the share."""
    known = codebook.lookup(column)
    coding = (known.coding or {}) if known else {}
    return [float(code) for code, label in coding.items() if label.lower() in _NON_ANSWER_LABELS]


def prevalence(ctx: Context) -> list[ExactItem]:
    weights = _weights(ctx)
    items = []
    for rule in ctx.pack.prevalence:
        column = ctx.column_for(rule.role)
        if column is None:
            continue
        values = _num(ctx.frame[column])
        values = values.where(~values.isin(_non_answers(column)))
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
                chart=(
                    BarChart(
                        x_label="group",
                        y_label=f"share with {rule.label}",
                        value_format="percent",
                        bars=[
                            Bar(
                                label=str(r["group"]),
                                value=float(r["share"] or 0),
                                n=int(r["n"] or 0),
                            )
                            for r in table
                        ],
                    )
                    if table
                    else None
                ),
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
        grouped = pd.DataFrame({"c": c[valid], "p": p[valid], "g": _segments(ctx)[valid]})
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
    "margins": margins,
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

# The analyst figures live in their own module, which needs the helpers above; importing it
# here, after they exist, is what lets the two modules share them.
from pramana.analysis.computed.analyst import ANALYST_ANALYSES  # noqa: E402

ANALYSES.update(ANALYST_ANALYSES)


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
    detected: SectorMatch | None = None,
) -> ComputedAnalysis:
    """Run the Exact tier on a cleaned table.

    Guarantees: deterministic for the same inputs; every analysis the pack lists runs
    independently, and one that raises becomes a "not run" item with a fixed message
    (the exception text is logged, never shown); nothing here calls a model.
    """
    config = config or load_computed_config()
    packs = load_packs() if packs is None else packs
    # `detected` is a match already made (by the sector model); otherwise the rules decide.
    match = detected or detect_sector(list(map(str, frame.columns)), packs, override=sector)
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
    items = _flag_incomplete_last_period(ctx, items)
    result = ComputedAnalysis(
        version=COMPUTED_VERSION,
        sector=match,
        shape=shape,
        scope_note=pack.wording.scope_note,
        items=items,
    )
    result = build_story(result, config)
    # The code-written summary is always there; a model rewording may replace it later.
    return result.model_copy(update={"summary": template_summary(result)})
