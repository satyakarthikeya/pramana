"""The facts the analyst agent may cite, all computed by code.

Exact figures, Measured results, a leaderboard of every model tried, and a table of how the
numeric columns move together (rank correlation on the whole table: described, not tested).
"""

from __future__ import annotations

import pandas as pd

from pramana.analysis.analyst.models import Fact
from pramana.analysis.claim_filters import redundant_correlation
from pramana.analysis.computed.models import ComputedAnalysis
from pramana.analysis.computed.summary import ranked
from pramana.analysis.measured.models import MeasuredAnalysis, MeasuredItem
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile

MAX_EXACT = 6
MAX_TABLE_ROWS = 8
MAX_PAIRS = 8
MIN_PAIR_ROWS = 10
MAX_COLUMNS = 30
_DRIVERS = {"driver_regression", "driver_classification"}


def _label(key: str) -> str:
    return key.replace("_", " ")


def leaderboard(item: MeasuredItem) -> Fact | None:
    """Every model family's held-out score for one prediction task, next to the baseline."""
    rows = []
    for key, value in item.values.items():
        if not key.startswith("held_out_") or not isinstance(value, int | float):
            continue
        family = key.removeprefix("held_out_")
        won = item.values.get(f"selected_{family}", 0)
        rows.append({"model": _label(family), "held_out_score": float(value), "folds_won": won})
    if not rows or item.baseline_score is None:
        return None
    rows.sort(key=lambda r: -float(r["held_out_score"]))
    return Fact(
        id=f"leaderboard:{item.target}",
        tier="measured",
        title=f"Every model tried for {item.target}, scored on rows it did not see",
        sentence=(
            f"Held-out {item.metric} for each model tried to predict {item.target}; the "
            f"{item.baseline} scored {item.baseline_score:.2f}."
        ),
        values={
            "baseline_score": item.baseline_score,
            "rows": item.n_rows,
            "folds": item.values.get("folds_scored"),
        },
        table=rows,
        columns=[item.target] if item.target else [],
    )


def associations(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    roles: dict[str, str],
    time_column: str | None,
) -> Fact | None:
    """Strongest rank correlations between numeric columns on the whole table (described)."""
    numeric = [
        name
        for name, profile in schema.columns.items()
        if profile.usable_for_hypotheses
        and profile.role is ColumnRole.NUMERIC
        and name in frame.columns
        and name != time_column
        and not profile.is_time_like
    ][:MAX_COLUMNS]
    time_like = {name: schema.columns[name].is_time_like for name in numeric}
    pairs = []
    for i, a in enumerate(numeric):
        for b in numeric[i + 1 :]:
            if redundant_correlation(a, b, roles, time_column=time_column, time_like=time_like):
                continue
            both = frame[[a, b]].apply(pd.to_numeric, errors="coerce").dropna()
            if len(both) < MIN_PAIR_ROWS or both[a].nunique() < 2 or both[b].nunique() < 2:
                continue
            rho = both[a].corr(both[b], method="spearman")
            if pd.notna(rho):
                pairs.append(
                    {
                        "column_a": a,
                        "column_b": b,
                        "rank_correlation": float(rho),
                        "rows": len(both),
                    }
                )
    if not pairs:
        return None
    pairs.sort(key=lambda p: -abs(float(p["rank_correlation"])))
    top = pairs[:MAX_PAIRS]
    return Fact(
        id="associations",
        tier="described",
        title="How the numeric columns move together",
        sentence=(
            f"Rank correlation between pairs of numeric columns over {len(frame)} rows. This "
            "describes the table; it is not a tested claim."
        ),
        values={"pairs_compared": len(pairs), "rows": len(frame)},
        table=top,
        columns=sorted({str(p[k]) for p in top for k in ("column_a", "column_b")}),
    )


def build_facts(
    computed: ComputedAnalysis | None,
    measured: MeasuredAnalysis | None,
    frame: pd.DataFrame,
    schema: SchemaProfile,
) -> list[Fact]:
    facts: list[Fact] = []
    roles = dict(computed.sector.roles) if computed else {}
    time_column = computed.shape.time_column if computed else None
    if (assoc := associations(frame, schema, roles, time_column)) is not None:
        facts.append(assoc)
    if measured is not None:
        for item in measured.items:
            if item.status not in {"ok", "no_lift"}:
                continue
            facts.append(
                Fact(
                    id=item.id,
                    tier="measured",
                    title=item.title,
                    sentence=item.sentence,
                    values=dict(item.values),
                    table=item.table[:MAX_TABLE_ROWS],
                    columns=[c for c in [item.target, *item.features] if c],
                )
            )
            if item.kind in _DRIVERS and (board := leaderboard(item)) is not None:
                facts.append(board)
    if computed is not None:
        for item in ranked(computed, MAX_EXACT):
            facts.append(
                Fact(
                    id=item.id,
                    tier="exact",
                    title=item.title,
                    sentence=item.sentence,
                    values=dict(item.values),
                    table=item.table[:MAX_TABLE_ROWS],
                    columns=[c for c in item.columns if c],
                )
            )
    return facts
