"""Planted-fact recall for the Exact tier's report (PLAN_data_analyst.md section 9).

Builds small seeded tables that each contain one or two facts an analyst would be
expected to report, runs the real `compute_analysis`, and scores whether each fact is
among the report's top findings with the right numbers. It measures that the report
SURFACES known facts. It does not show that the report finds true unknown ones, and the
tables are synthetic.

    python scripts/calibration/analyst_recall.py [--top 8]
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from pramana.analysis import infer_schema, load_config
from pramana.analysis.computed import ComputedAnalysis, ExactItem, compute_analysis
from pramana.analysis.computed.summary import ranked

SEED = 20261025
TOP = 8


@dataclass(frozen=True)
class Fact:
    name: str
    found: Callable[[list[ExactItem]], bool]


@dataclass(frozen=True)
class Case:
    name: str
    table: Callable[[], pd.DataFrame]
    facts: list[Fact]
    #: Kinds of figure that speak to this table's planted facts; others are "other".
    relevant: frozenset[str]


# --- tables -------------------------------------------------------------------------


def _grid(months: str, end: str, regions, products=("Core", "Lite")) -> list[dict]:
    return [
        {"month": m.to_timestamp().date().isoformat(), "region": r, "product": p}
        for m in pd.period_range(months, end, freq="M")
        for r in regions
        for p in products
    ]


def margin_table() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = _grid("2023-01", "2024-12", ("North", "South", "East"))
    for r in rows:
        r["revenue"] = 1000 * rng.uniform(0.95, 1.05)
        worse = r["product"] == "Lite" and r["month"] >= "2024-01"
        r["cost"] = r["revenue"] * (0.75 if worse else 0.60)
    return pd.DataFrame(rows)


def season_table() -> pd.DataFrame:
    rng = np.random.default_rng(SEED + 1)
    rows = _grid("2022-01", "2024-12", ("North", "South"))
    for r in rows:
        month = int(r["month"][5:7])
        r["revenue"] = 1000 * rng.uniform(0.97, 1.03) * (1.35 if month >= 10 else 1.0)
        r["cost"] = r["revenue"] * 0.6
    return pd.DataFrame(rows)


def spike_table() -> pd.DataFrame:
    rng = np.random.default_rng(SEED + 2)
    rows = _grid("2023-01", "2024-12", ("North", "South", "East"))
    for r in rows:
        r["revenue"] = 1000 * rng.uniform(0.95, 1.05)
        r["cost"] = r["revenue"] * 0.6
    frame = pd.DataFrame(rows)
    frame.loc[31, "revenue"] *= 6
    return frame


def collapse_table() -> pd.DataFrame:
    rng = np.random.default_rng(SEED + 3)
    rows = _grid("2023-01", "2024-12", ("Denmark", "France", "Spain", "South", "Italy"), ("Core",))
    for r in rows:
        year2 = r["month"] >= "2024-01"
        level = {"Denmark": 0.2 if year2 else 1.0, "South": 1.3 if year2 else 1.0}.get(r["region"], 1.0)
        r["revenue"] = 1000 * level * rng.uniform(0.97, 1.03)
        r["cost"] = r["revenue"] * 0.6
    return pd.DataFrame(rows)


def price_volume_table() -> pd.DataFrame:
    """Year two: Core's price is up 20% but its units are down 25%; Lite is unchanged."""
    rng = np.random.default_rng(SEED + 4)
    rows = _grid("2023-01", "2024-12", ("North", "South"))
    for r in rows:
        year2 = r["month"] >= "2024-01"
        core = r["product"] == "Core"
        units = 100 * rng.uniform(0.97, 1.03) * (0.75 if (core and year2) else 1.0)
        price = 10.0 * (1.2 if (core and year2) else 1.0)
        r["units"], r["price"] = units, price
        r["revenue"] = units * price
    return pd.DataFrame(rows)


def customer_table() -> pd.DataFrame:
    """Transactions: ten of a hundred customers make about half of the revenue."""
    rng = np.random.default_rng(SEED + 5)
    rows = []
    for day in pd.date_range("2023-01-01", "2024-12-28", freq="2D"):
        for _ in range(6):
            big = rng.random() < 0.5
            customer = int(rng.integers(1, 11)) if big else int(rng.integers(11, 101))
            rows.append(
                {
                    "order_date": day.date().isoformat(),
                    "customer": f"C{customer:03d}",
                    "region": str(rng.choice(["North", "South"])),
                    "revenue": (revenue := float(rng.uniform(40, 60))),
                    "cost": revenue * 0.6,
                }
            )
    return pd.DataFrame(rows)


# --- facts --------------------------------------------------------------------------


def _of(items: list[ExactItem], kind: str) -> list[ExactItem]:
    return [i for i in items if i.kind == kind and i.status == "ok"]


def _margin_names_lite(items: list[ExactItem]) -> bool:
    return any(
        i.table and i.table[0].get("level") == "Lite" and (i.values.get("change_points") or 0) < 0
        for i in _of(items, "margins")
    )


def _season_in_q4(items: list[ExactItem]) -> bool:
    return any(
        (i.values.get("peak_month") in (10, 11, 12)) and (i.values.get("peak_index") or 0) > 1.15
        for i in _of(items, "seasonality")
    )


def _spike_listed(items: list[ExactItem]) -> bool:
    return any(
        (row.get("times_median") or 0) > 4
        for i in _of(items, "outliers")
        for row in i.table
    )


def _collapse_named(items: list[ExactItem]) -> bool:
    for i in _of(items, "variance_decomposition"):
        fell = [r for r in i.table if (r.get("change") or 0) < 0]
        if fell and min(fell, key=lambda r: r["change"]).get("segment") == "Denmark":
            return True
    return False


def _fastest_grower(items: list[ExactItem]) -> bool:
    return any(i.values.get("fastest_segment") == "South" for i in _of(items, "segment_growth"))


def _price_vs_volume(items: list[ExactItem]) -> bool:
    return any(
        (i.values.get("price_effect") or 0) > 0 and (i.values.get("volume_effect") or 0) < 0
        for i in _of(items, "price_volume_mix")
    )


def _top_customers(items: list[ExactItem]) -> bool:
    return any(0.35 <= (i.values.get("top_n_share") or 0) <= 0.65 for i in _of(items, "customer_view"))


CASES = [
    Case("margin falls on one product", margin_table, [Fact("Lite margin fall named", _margin_names_lite)],
         frozenset({"margins", "period_change"})),
    Case("Q4 is 35% higher", season_table, [Fact("Q4 peak found", _season_in_q4)],
         frozenset({"seasonality"})),
    Case("one row six times too large", spike_table, [Fact("inflated row listed", _spike_listed)],
         frozenset({"outliers"})),
    Case("one segment collapses, one grows", collapse_table,
         [Fact("collapse named", _collapse_named), Fact("fastest grower named", _fastest_grower)],
         frozenset({"variance_decomposition", "segment_growth", "period_change"})),
    Case("price up, volume down", price_volume_table, [Fact("price vs volume split", _price_vs_volume)],
         frozenset({"price_volume_mix", "period_change", "variance_decomposition"})),
    Case("ten customers make half", customer_table, [Fact("top-customer share found", _top_customers)],
         frozenset({"customer_view", "concentration"})),
]


# --- scoring ------------------------------------------------------------------------


def top_findings(result: ComputedAnalysis, k: int) -> list[ExactItem]:
    """The report's lead findings: the story order when the report has one, otherwise
    the older summary ranking."""
    story = getattr(result, "story", None)
    if story is not None:
        by_id = {i.id: i for i in result.items}
        return [by_id[i] for i in story.lead_ids if i in by_id][:k]
    return ranked(result, k)


def score(top: int = TOP) -> dict:
    config = load_config().schema_inference
    rows, found_total, fact_total, other, listed = [], 0, 0, 0, 0
    for case in CASES:
        frame = case.table()
        result = compute_analysis(frame, infer_schema(frame, config))
        lead = top_findings(result, top)
        facts = {f.name: bool(f.found(lead)) for f in case.facts}
        off = [i.id for i in lead if i.kind not in case.relevant]
        found_total += sum(facts.values())
        fact_total += len(facts)
        other += len(off)
        listed += len(lead)
        rows.append({"table": case.name, "facts": facts, "lead_kinds": [i.kind for i in lead], "off_topic": off})
    return {
        "top": top,
        "recall": found_total / fact_total,
        "found": found_total,
        "facts": fact_total,
        "off_topic_per_report": other / len(CASES),
        "lead_items_per_report": listed / len(CASES),
        "rows": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=TOP)
    out = score(parser.parse_args().top)
    for r in out["rows"]:
        print(f"{r['table']:<36} {r['facts']}  off-topic={len(r['off_topic'])}")
    print(
        f"recall {out['found']}/{out['facts']} = {out['recall']:.2f} | off-topic per report "
        f"{out['off_topic_per_report']:.1f} of {out['lead_items_per_report']:.1f} lead items (top {out['top']})"
    )
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}))
