"""Check a structured statement against the table: recompute it, and say how it compares.

Every figure here is arithmetic on the user's rows. The wording of each verdict is written by
code from those figures. A statement a table cannot settle (a cause, a projection) is said
to be not testable, with the reason, and never given a quiet pass.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import pandas as pd

from pramana.analysis.statements.models import (
    AssociationStatement,
    CausalStatement,
    ChangeStatement,
    CheckResult,
    ForecastStatement,
    Granularity,
    RankStatement,
    Reading,
    ShareStatement,
    Statement,
)

#: A stated percentage that is within this many points of the table's figure counts as matching.
TOLERANCE_POINTS = 0.5
_FREQ = {"month": "M", "quarter": "Q", "year": "Y"}
_YEAR_AGO = {"month": 12, "quarter": 4, "year": 1}
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.1f}%"


def _number(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce")


def _keys(frame: pd.DataFrame, time_column: str, granularity: Granularity) -> pd.Series | None:
    """Each row's period at the stated grain, or None when the time column cannot give it."""
    raw = frame[time_column]
    numbers = pd.to_numeric(raw, errors="coerce")
    if numbers.notna().all() and bool(numbers.between(1800, 2200).all()):
        if granularity != "year":
            return None
        return pd.Series(pd.PeriodIndex(numbers.astype(int), freq="Y"), index=frame.index)
    stamps = pd.to_datetime(raw, errors="coerce")
    if stamps.isna().all():
        return None
    return stamps.dt.to_period(_FREQ[granularity])


def parse_period(label: str, granularity: Granularity) -> pd.Period | None:
    text = label.strip()
    if granularity == "year":
        match = re.fullmatch(r"(?:FY\s*)?(\d{4})", text, re.IGNORECASE)
        return pd.Period(int(match.group(1)), freq="Y") if match else None
    if granularity == "quarter":
        match = re.fullmatch(
            r"(\d{4})\s*-?\s*Q([1-4])|Q([1-4])\s*-?\s*(\d{4})", text, re.IGNORECASE
        )
        if not match:
            return None
        year, quarter = (
            (match.group(1), match.group(2)) if match.group(1) else (match.group(4), match.group(3))
        )
        return pd.Period(f"{year}Q{quarter}", freq="Q")
    match = re.fullmatch(r"(\d{4})[-/](\d{1,2})", text)
    if match and 1 <= int(match.group(2)) <= 12:
        return pd.Period(f"{match.group(1)}-{int(match.group(2)):02d}", freq="M")
    match = re.fullmatch(r"([A-Za-z]{3,9})\.?\s+(\d{4})", text)
    if match and match.group(1)[:3].lower() in _MONTHS:
        return pd.Period(f"{match.group(2)}-{_MONTHS[match.group(1)[:3].lower()]:02d}", freq="M")
    return None


def _aggregate(values: pd.Series, additive: bool) -> float | None:
    clean = values.dropna()
    if clean.empty:
        return None
    return float(clean.sum() if additive else clean.mean())


def _change(
    s: ChangeStatement, frame: pd.DataFrame, time_column: str | None, additive: bool
) -> CheckResult:
    if s.measure not in frame.columns:
        return _cannot("change", f"There is no column called {s.measure}.")
    if time_column is None or time_column not in frame.columns:
        return _cannot(
            "change", "This table has no time column, so a change over time cannot be checked."
        )
    keys = _keys(frame, time_column, s.granularity)
    if keys is None:
        return _cannot("change", f"The time column cannot be read by {s.granularity}.")
    to = parse_period(s.to_period, s.granularity)
    if to is None:
        return _cannot("change", f"{s.to_period!r} is not a {s.granularity} the table can read.")
    values = _number(frame, s.measure)
    by_period = {
        p: _aggregate(values[keys == p], additive)
        for p in {to, to - 1, to - _YEAR_AGO[s.granularity]}
    }
    explicit = parse_period(s.from_period, s.granularity) if s.from_period else None
    if s.from_period and explicit is None:
        return _cannot("change", f"{s.from_period!r} is not a {s.granularity} the table can read.")
    if explicit is not None and explicit not in by_period:
        by_period[explicit] = _aggregate(values[keys == explicit], additive)
    now = by_period[to]
    if now is None:
        return _cannot("change", f"The table has no {s.measure} values for {to}.")

    def reading(base: pd.Period, label: str) -> Reading:
        before = by_period.get(base)
        pct = None if before is None or before <= 0 else 100.0 * (now - before) / before
        return Reading(
            label=f"{to} versus {base}{label}",
            value=pct,
            matches=pct is not None
            and s.stated_pct is not None
            and abs(pct - s.stated_pct) < TOLERANCE_POINTS,
        )

    previous = reading(to - 1, " (the previous period)")
    year_ago = reading(to - _YEAR_AGO[s.granularity], " (the same period a year earlier)")
    stated = (
        reading(explicit, " (as stated)")
        if explicit is not None
        else (previous if s.baseline == "previous" else year_ago)
    )
    others = [r for r in (previous, year_ago) if r.label != stated.label]
    readings = [stated, *others]
    values_out = {"to_period": str(to), "measure": s.measure, "stated_pct": s.stated_pct}
    if s.stated_pct is None:
        return CheckResult(
            kind="change",
            status="cannot_check",
            readings=readings,
            values=values_out,
            headline="No figure was stated to check. The table gives "
            + "; ".join(f"{r.label}: {_pct(r.value)}" for r in readings),
        )
    if stated.value is None:
        return _cannot("change", "The comparison period has no data or a zero or negative base.")
    if stated.matches:
        return CheckResult(
            kind="change",
            status="matches",
            readings=readings,
            values=values_out,
            headline=f"Matches: {stated.label} the table gives {_pct(stated.value)}, "
            f"and the statement says {_pct(s.stated_pct)}.",
        )
    alternate = next((r for r in others if r.matches), None)
    if alternate is not None:
        return CheckResult(
            kind="change",
            status="ambiguous",
            readings=readings,
            values=values_out,
            headline=f"It matches only under a different reading: {alternate.label} the table gives "
            f"{_pct(alternate.value)}. Read as {stated.label} it is {_pct(stated.value)}.",
        )
    gap = abs(stated.value - s.stated_pct)
    return CheckResult(
        kind="change",
        status="off_by",
        readings=readings,
        values={**values_out, "off_by_points": gap},
        headline=f"Off by {gap:.1f} points: {stated.label} the table gives {_pct(stated.value)}, "
        f"not {_pct(s.stated_pct)}.",
    )


def _groups(frame: pd.DataFrame, column: str, measure: str, additive: bool) -> pd.Series | None:
    if column not in frame.columns or measure not in frame.columns:
        return None
    values = _number(frame, measure)
    keys = frame[column].astype(str)
    grouped = values.groupby(keys)
    return (grouped.sum(min_count=1) if additive else grouped.mean()).dropna()


def _find_group(table: pd.Series, group: str) -> str | None:
    lowered = {str(k).lower(): str(k) for k in table.index}
    return lowered.get(group.strip().lower())


def _share(s: ShareStatement, frame: pd.DataFrame, additive: bool) -> CheckResult:
    if not additive:
        return _cannot(
            "share",
            f"{s.measure} is not a total that parts add up to, so a share is not meaningful.",
        )
    table = _groups(frame, s.group_column, s.measure, additive=True)
    if table is None or table.sum() <= 0:
        return _cannot("share", f"There is no usable {s.measure} by {s.group_column}.")
    name = _find_group(table, s.group)
    if name is None:
        return _cannot(
            "share",
            f"{s.group_column} has no group called {s.group!r}. Groups include "
            + ", ".join(map(str, list(table.index)[:6]))
            + ".",
        )
    pct = 100.0 * float(table[name]) / float(table.sum())
    reading = Reading(
        label=f"{name} share of {s.measure}",
        value=pct,
        matches=s.stated_pct is not None and abs(pct - s.stated_pct) < TOLERANCE_POINTS,
    )
    values = {"group": name, "share_pct": pct, "stated_pct": s.stated_pct}
    if s.stated_pct is None:
        return CheckResult(
            kind="share",
            status="cannot_check",
            readings=[reading],
            values=values,
            headline=f"No figure was stated. {name} is {pct:.1f}% of {s.measure}.",
        )
    if reading.matches:
        return CheckResult(
            kind="share",
            status="matches",
            readings=[reading],
            values=values,
            headline=f"Matches: {name} is {pct:.1f}% of {s.measure}; the statement says {s.stated_pct:g}%.",
        )
    gap = abs(pct - s.stated_pct)
    return CheckResult(
        kind="share",
        status="off_by",
        readings=[reading],
        values={**values, "off_by_points": gap},
        headline=f"Off by {gap:.1f} points: {name} is {pct:.1f}% of {s.measure}, not {s.stated_pct:g}%.",
    )


def _rank(s: RankStatement, frame: pd.DataFrame, additive: bool) -> CheckResult:
    table = _groups(frame, s.group_column, s.measure, additive)
    if table is None or table.empty:
        return _cannot("rank", f"There is no usable {s.measure} by {s.group_column}.")
    name = _find_group(table, s.group)
    if name is None:
        return _cannot("rank", f"{s.group_column} has no group called {s.group!r}.")
    ordered = table.sort_values(ascending=s.position == "lowest")
    actual = str(ordered.index[0])
    how = "total" if additive else "average"
    board = [
        Reading(label=str(k), value=float(v), matches=str(k) == name)
        for k, v in ordered.head(5).items()
    ]
    values = {"actual": actual, "claimed": name, "position": s.position}
    if actual == name:
        return CheckResult(
            kind="rank",
            status="matches",
            readings=board,
            values=values,
            headline=f"Matches: {name} has the {s.position} {how} {s.measure} ({float(table[name]):,.2f}).",
        )
    return CheckResult(
        kind="rank",
        status="off_by",
        readings=board,
        values=values,
        headline=f"Not so: {actual} has the {s.position} {how} {s.measure} ({float(table[actual]):,.2f}); "
        f"{name} has {float(table[name]):,.2f}.",
    )


def _association(s: AssociationStatement, tested: Sequence[dict[str, Any]]) -> CheckResult:
    pair = {s.x, s.y}
    for item in tested:
        if {item.get("x"), item.get("y")} == pair:
            return CheckResult(
                kind="association",
                status="tested",
                headline=f"The verification gateway tested this and the verdict was {item.get('verdict')}"
                + (f" (q = {item['q']:.4f})" if isinstance(item.get("q"), float) else "")
                + ". See the Checked claims tab for the proof.",
                values={"verdict": str(item.get("verdict"))},
            )
    return CheckResult(
        kind="association",
        status="not_tested",
        headline=f"This has not been tested yet. Run Analyse: the gateway can test whether "
        f"{s.x} and {s.y} go together, with a multiple-testing correction and robustness checks.",
    )


def _causal(s: CausalStatement) -> CheckResult:
    return CheckResult(
        kind="causal",
        status="not_testable",
        headline=f"A table cannot show that {s.cause} causes {s.effect}.",
        detail=f"It can show whether they move together. Showing a cause needs an experiment, or a "
        f"comparison of similar cases with and without {s.cause} where {s.effect} is measured before "
        "and after, and a way to rule out other explanations.",
    )


def _forecast(s: ForecastStatement) -> CheckResult:
    return CheckResult(
        kind="forecast",
        status="not_testable",
        headline=f"A projection of {s.measure} cannot be checked against this table.",
        detail="Nobody can verify the future. It can be judged two ways: how the same method would "
        "have done on past periods (a backtest), and by comparing it with the real figure when it arrives.",
    )


def _cannot(kind: str, why: str) -> CheckResult:
    return CheckResult(kind=kind, status="cannot_check", headline=why)


def check_statement(
    statement: Statement,
    frame: pd.DataFrame,
    *,
    time_column: str | None,
    additive: bool,
    tested: Sequence[dict[str, Any]] = (),
) -> CheckResult:
    """Recompute one statement from the table. Never raises for a statement the table cannot serve."""
    try:
        if isinstance(statement, ChangeStatement):
            return _change(statement, frame, time_column, additive)
        if isinstance(statement, ShareStatement):
            return _share(statement, frame, additive)
        if isinstance(statement, RankStatement):
            return _rank(statement, frame, additive)
        if isinstance(statement, AssociationStatement):
            return _association(statement, tested)
        if isinstance(statement, CausalStatement):
            return _causal(statement)
        return _forecast(statement)
    except (ValueError, KeyError, TypeError, OverflowError):
        return _cannot(statement.kind, "This statement could not be checked against the table.")
