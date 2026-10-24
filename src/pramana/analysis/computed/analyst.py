"""Analyst figures for the Exact tier: price/volume/mix, segment growth, customers.

Same rules as `runner`: arithmetic on the table, a code-written sentence, the formula
beside it, and every number in a sentence also in `values` or `table`. Nothing here
calls a model or reaches the gateway.

This module is imported by `runner` after its helpers exist and by nothing else.
"""

from __future__ import annotations

import re

import pandas as pd

from pramana.analysis.computed.charts import Bar, BarChart, WaterfallChart, WaterfallStep
from pramana.analysis.computed.models import ExactItem
from pramana.analysis.computed.runner import (
    Context,
    _fmt,
    _not_run,
    _num,
    _pick,
    _row,
    _segments,
    _windows,
)

_QUANTITY_NAME = r"unit|qty|quantit|volume"
_CUSTOMER_NAME = re.compile(r"customer|client", re.IGNORECASE)
_ID_TOKEN = re.compile(r"(?:^|[^a-z])(?:id|code|key|no|number)(?:[^a-z]|$)", re.IGNORECASE)


def _signed(value: float) -> str:
    return f"+{_fmt(value)}" if value >= 0 else f"−{_fmt(abs(value))}"


def _amount_and_quantity(ctx: Context) -> tuple[str | None, str | None]:
    amount = _pick(ctx, "amount", r"revenue|sales")
    quantity = _pick(ctx, "quantity", _QUANTITY_NAME)
    if quantity is not None and amount is not None and quantity == amount:
        quantity = None
    return amount, quantity


# --- price / volume / mix ------------------------------------------------------------


def price_volume_mix(ctx: Context) -> list[ExactItem]:
    """Split the change in an amount into volume, price and mix, with the parts adding up
    to the change exactly.

    Per segment s, with units q and amount r, price p = r / q in the earlier window (0) and
    the later one (1), over segments with units and amount in BOTH windows:

        volume = (Q1 - Q0) * (R0 / Q0)                 the whole table sells more or fewer units
        mix    = sum_s (q1_s - Q1 * q0_s / Q0) * p0_s  units moved between cheap and dear segments
        price  = sum_s q1_s * (p1_s - p0_s)            each segment's own price per unit

    Segments present in only one window, or with no units or no amount, have no price to
    compare; their whole change is reported on its own line so the total still adds up.
    """
    if ctx.keys is None or ctx.group is None:
        return []
    amount, quantity = _amount_and_quantity(ctx)
    if amount is None:
        return []
    if quantity is None:
        return [_not_run("price_volume_mix", "Needs a units (quantity) column beside the amount.", amount)]
    windows = _windows(ctx)
    if windows is None:
        return []
    current, previous, cur_label, prev_label = windows
    money, units = _num(ctx.frame[amount]), _num(ctx.frame[quantity])
    both = money.notna() & units.notna()
    segment = _segments(ctx)

    def window(periods: list[object]) -> tuple[pd.Series, pd.Series]:
        mask = ctx.keys.isin(periods) & both
        return (
            money[mask].groupby(segment[mask]).sum(),
            units[mask].groupby(segment[mask]).sum(),
        )

    r0, q0 = window(previous)
    r1, q1 = window(current)
    table = pd.DataFrame({"r0": r0, "q0": q0, "r1": r1, "q1": q1}).fillna(0.0)
    comparable = (table[["r0", "q0", "r1", "q1"]] > 0).all(axis=1)
    inside, outside = table[comparable], table[~comparable]
    if len(inside) < 1:
        return [
            _not_run(
                "price_volume_mix",
                f"No {ctx.group} value has both units and {amount} in both windows.",
                amount,
            )
        ]
    total_change = float(table["r1"].sum() - table["r0"].sum())
    if total_change == 0:
        return [_not_run("price_volume_mix", f"Total {amount} did not change.", amount)]
    q0_all, q1_all, r0_all = float(inside["q0"].sum()), float(inside["q1"].sum()), float(inside["r0"].sum())
    p0 = inside["r0"] / inside["q0"]
    p1 = inside["r1"] / inside["q1"]
    volume_s = (q1_all * inside["q0"] / q0_all - inside["q0"]) * p0
    mix_s = (inside["q1"] - q1_all * inside["q0"] / q0_all) * p0
    price_s = inside["q1"] * (p1 - p0)
    volume, mix, price = float(volume_s.sum()), float(mix_s.sum()), float(price_s.sum())
    other = float((outside["r1"] - outside["r0"]).sum())
    # The parts add up to the change by algebra; a mismatch is a bug, never rounded away.
    assert abs(volume + mix + price + other - total_change) <= 1e-6 * max(1.0, abs(total_change))

    movement = "rose" if total_change > 0 else "fell"
    parts = f"volume {_signed(volume)}, price {_signed(price)} and mix {_signed(mix)}"
    sentence = (
        f"Total {amount} {movement} by {_fmt(abs(total_change))} from {prev_label} to {cur_label}: "
        f"{parts}"
        + (f", and {len(outside)} {ctx.group} value(s) in only one window {_signed(other)}" if len(outside) else "")
        + "."
    )
    detail = pd.DataFrame(
        {"volume": volume_s, "price": price_s, "mix": mix_s, "price_per_unit_before": p0, "price_per_unit_now": p1}
    )
    detail["change"] = detail["volume"] + detail["price"] + detail["mix"]
    detail = detail.reindex(detail["change"].abs().sort_values(ascending=False).index)
    shown = detail.iloc[: ctx.config.max_segments]
    time = ctx.shape.time_column or ""
    return [
        ExactItem(
            id=f"price_volume_mix:{amount}:{quantity}",
            kind="price_volume_mix",
            title="Price, volume and mix",
            sentence=sentence,
            formula="volume = (Q1 − Q0) × (R0 ÷ Q0); price = Σ q1 × (p1 − p0); "
            "mix = Σ (q1 − Q1 × q0 ÷ Q0) × p0; p = amount ÷ units per "
            f"{ctx.group}; the parts add up to the change",
            columns=[amount, quantity, ctx.group, time],
            filters=[f"{time} in {cur_label}", f"{time} in {prev_label}"],
            n_rows=int((ctx.keys.isin(current + previous) & both).sum()),
            values={
                "total_change": total_change,
                "volume_effect": volume,
                "price_effect": price,
                "mix_effect": mix,
                "other_effect": other,
                "segments_compared": len(inside),
                "segments_in_one_window": len(outside),
                "units_before": q0_all,
                "units_now": q1_all,
                "price_per_unit_before": r0_all / q0_all,
                "price_per_unit_now": float(inside["r1"].sum()) / q1_all,
            },
            table=[
                _row(
                    segment=name,
                    volume=r["volume"],
                    price=r["price"],
                    mix=r["mix"],
                    change=r["change"],
                    price_per_unit_before=r["price_per_unit_before"],
                    price_per_unit_now=r["price_per_unit_now"],
                )
                for name, r in shown.iterrows()
            ],
            chart=WaterfallChart(
                y_label=f"total {amount}",
                start_label=prev_label,
                end_label=cur_label,
                start=float(table["r0"].sum()),
                end=float(table["r1"].sum()),
                steps=[
                    WaterfallStep(label=label, value=value)
                    for label, value in (
                        ("Volume", volume),
                        ("Price", price),
                        ("Mix", mix),
                        ("Only in one window", other),
                    )
                    if label != "Only in one window" or len(outside)
                ],
            ),
        )
    ]


# --- segment growth ------------------------------------------------------------------


def segment_growth(ctx: Context) -> list[ExactItem]:
    """Growth rate of the main amount per segment, between the two windows, ranked.

    A segment under `segment_growth_min_share` of the earlier total is left out of the
    ranking (a tiny base makes any rate look dramatic) and counted on the item.
    """
    if ctx.keys is None or ctx.group is None:
        return []
    amount = _pick(ctx, "amount", r"revenue|sales") or (ctx.measures[0] if ctx.measures else None)
    if amount is None:
        return []
    windows = _windows(ctx)
    if windows is None:
        return []
    current, previous, cur_label, prev_label = windows
    values = _num(ctx.frame[amount])
    segment = _segments(ctx)
    now = values[ctx.keys.isin(current)].groupby(segment[ctx.keys.isin(current)]).sum()
    before = values[ctx.keys.isin(previous)].groupby(segment[ctx.keys.isin(previous)]).sum()
    table = pd.DataFrame({"previous": before, "current": now}).fillna(0.0)
    total_before, total_now = float(table["previous"].sum()), float(table["current"].sum())
    if total_before <= 0:
        return [_not_run("segment_growth", f"Total {amount} in {prev_label} is not positive.", amount)]
    eligible = table[(table["previous"] > 0) & (table["previous"] >= ctx.config.segment_growth_min_share * total_before)]
    if len(eligible) < 2:
        return [
            _not_run(
                "segment_growth",
                f"Fewer than two {ctx.group} values have a large enough base in {prev_label}.",
                amount,
            )
        ]
    growth = (eligible["current"] / eligible["previous"] - 1.0).sort_values(ascending=False, kind="stable")
    overall = total_now / total_before - 1.0
    fastest, slowest = str(growth.index[0]), str(growth.index[-1])
    f_pct, s_pct = 100 * float(growth.iloc[0]), 100 * float(growth.iloc[-1])
    left_out = len(table) - len(eligible)
    if f_pct == s_pct:
        return [_not_run("segment_growth", f"No {ctx.group} value differs in growth rate from the others.", amount)]

    def move(pct: float) -> str:
        return f"{'up' if pct >= 0 else 'down'} {abs(pct):.1f}%"

    sentence = (
        f"From {prev_label} to {cur_label}, {amount} in {fastest} was {move(f_pct)}, the fastest of "
        f"{len(eligible)} {ctx.group} values, and in {slowest} {move(s_pct)}, the slowest; the "
        f"total across {ctx.group} values was {move(100 * overall)}."
    )
    time = ctx.shape.time_column or ""
    return [
        ExactItem(
            id=f"segment_growth:{amount}",
            kind="segment_growth",
            title="Growth by segment",
            sentence=sentence,
            formula=f"growth = {amount}(current) ÷ {amount}(previous) − 1, per {ctx.group}; "
            f"values under {100 * ctx.config.segment_growth_min_share:g}% of the earlier total are not ranked",
            columns=[amount, ctx.group, time],
            filters=[f"{time} in {cur_label}", f"{time} in {prev_label}"],
            n_rows=int((ctx.keys.isin(current) | ctx.keys.isin(previous)).sum()),
            values={
                "fastest_segment": fastest,
                "fastest_pct": f_pct,
                "slowest_segment": slowest,
                "slowest_pct": s_pct,
                "overall_pct": 100 * overall,
                "spread_points": f_pct - s_pct,
                "segments_ranked": len(eligible),
                "segments_left_out": left_out,
            },
            table=[
                _row(
                    segment=name,
                    previous=eligible.loc[name, "previous"],
                    current=eligible.loc[name, "current"],
                    growth_pct=100 * g,
                )
                for name, g in growth.items()
            ][: max(ctx.config.max_segments, 2)],
            chart=BarChart(
                x_label=ctx.group,
                y_label=f"growth in {amount}",
                value_format="percent",
                bars=[Bar(label=str(name), value=float(g)) for name, g in growth.items()][: ctx.config.max_segments],
            ),
        )
    ]


# --- customers -----------------------------------------------------------------------


def _customer_column(ctx: Context) -> str | None:
    """A column of customer identifiers: named like a customer and either text or named
    like an id. A numeric `customers` column is a count per row, not an identifier."""
    for column in ctx.frame.columns:
        name = str(column)
        if not _CUSTOMER_NAME.search(name):
            continue
        if not pd.api.types.is_numeric_dtype(ctx.frame[column]) or _ID_TOKEN.search(name):
            return column
    return None


def customer_view(ctx: Context) -> list[ExactItem]:
    """How concentrated and how loyal the customer base is, when rows carry a customer id.

    Rows with no customer id are left out and their share reported, never counted as one
    customer. Customer totals are net of negative amounts; shares are of the positive
    total. "New" means first seen in this table inside the current window, so it is only
    given when an earlier window exists.
    """
    column = _customer_column(ctx)
    if column is None:
        return []
    amount = _pick(ctx, "amount", r"revenue|sales") or (ctx.measures[0] if ctx.measures else None)
    if amount is None:
        return []
    ids = ctx.frame[column]
    money = _num(ctx.frame[amount])
    known = ids.notna() & money.notna()
    missing_share = float((ids.isna()).mean())
    n_customers = int(ids[known].nunique())
    if n_customers < ctx.config.customer_min_customers:
        return [
            _not_run(
                "customer_view",
                f"Needs at least {ctx.config.customer_min_customers} distinct {column} values; found {n_customers}.",
                column,
            )
        ]
    per_customer = money[known].groupby(ids[known].astype(str)).sum().sort_values(ascending=False, kind="stable")
    positive_total = float(per_customer[per_customer > 0].sum())
    if positive_total <= 0:
        return [_not_run("customer_view", f"Total {amount} by customer is not positive.", column)]
    top_n = min(ctx.config.customer_top_n, len(per_customer))
    top_n_share = float(per_customer.iloc[:top_n].clip(lower=0).sum()) / positive_total
    decile = max(1, n_customers // 10)
    decile_share = float(per_customer.iloc[:decile].clip(lower=0).sum()) / positive_total
    values: dict[str, object] = {
        "customers": n_customers,
        "top_n": top_n,
        "top_n_share": top_n_share,
        "top_decile_share": decile_share,
        "top_decile_customers": decile,
        "rows_without_id_share": missing_share,
        "top_customer": str(per_customer.index[0]),
        "top_customer_share": float(max(per_customer.iloc[0], 0.0)) / positive_total,
    }
    sentence = f"Of {n_customers:,} customers, the top {top_n} account for {100 * top_n_share:.1f}% of {amount}"
    if decile != top_n:
        sentence += f" and the top tenth ({decile:,}) for {100 * decile_share:.1f}%"
    sentence += "."
    table: list[dict[str, object]] = [
        _row(customer=name, total=float(total), share=float(max(total, 0.0)) / positive_total)
        for name, total in per_customer.iloc[: min(top_n, 10)].items()
    ]
    if ctx.keys is not None:
        key = ctx.keys.astype("string")
        active = key[known].groupby(ids[known].astype(str)).nunique()
        repeat_share = float((active > 1).mean())
        values["repeat_share"] = repeat_share
        sentence += f" {100 * repeat_share:.1f}% of customers bought in more than one {ctx.shape.period or 'period'}."
        windows = _windows(ctx)
        if windows is not None:
            current, previous, cur_label, _ = windows
            first = key[known].groupby(ids[known].astype(str)).min()
            order = sorted(set(key.dropna()))
            earliest_current = min(str(p) for p in current)
            if earliest_current > order[0]:
                in_cur = ctx.keys.isin(current) & known
                new_ids = set(first[first >= earliest_current].index)
                cur_money = money[in_cur].groupby(ids[in_cur].astype(str)).sum()
                cur_total = float(cur_money.clip(lower=0).sum())
                if cur_total > 0:
                    new_money = float(cur_money[cur_money.index.isin(new_ids)].clip(lower=0).sum())
                    values["new_share_current"] = new_money / cur_total
                    values["returning_share_current"] = 1.0 - new_money / cur_total
                    values["new_customers_current"] = int(cur_money.index.isin(new_ids).sum())
                    values["returning_customers_current"] = int((~cur_money.index.isin(new_ids)).sum())
                    sentence += (
                        f" In {cur_label}, customers first seen then brought {100 * new_money / cur_total:.1f}% "
                        f"of {amount} and returning customers {100 * (1 - new_money / cur_total):.1f}%."
                    )
    if missing_share > 0:
        sentence += f" {100 * missing_share:.1f}% of rows have no {column} and are left out."
    return [
        ExactItem(
            id=f"customer_view:{column}",
            kind="customer_view",
            title="Customers",
            sentence=sentence,
            formula=f"share = customer total ÷ sum of positive customer totals; customers = distinct {column}",
            columns=[column, amount, ctx.shape.time_column or ""],
            n_rows=int(known.sum()),
            values={k: _row(v=v)["v"] for k, v in values.items()},
            table=table,
            chart=BarChart(
                x_label=column,
                y_label=f"share of {amount}",
                value_format="percent",
                bars=[Bar(label=str(r["customer"]), value=float(r["share"])) for r in table],
            ),
        )
    ]


ANALYST_ANALYSES = {
    "price_volume_mix": price_volume_mix,
    "segment_growth": segment_growth,
    "customer_view": customer_view,
}
