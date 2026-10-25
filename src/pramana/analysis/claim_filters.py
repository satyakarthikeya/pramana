"""Claims that would only restate the table's own bookkeeping (docs/PLAN_data_analyst.md s5).

Applied BEFORE a claim is rendered, so a dropped claim never reaches the gateway and never
changes the multiple-testing family; the planner records each drop with its reason where
the reader can see it. Code only, from column roles and names; no model.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

#: Roles that are built from each other (profit = amount - cost; amount = quantity x price).
_MONEY = {"amount", "cost", "profit"}
_VOLUME = {"quantity", "price"}
#: Names that count what an amount is made of, whatever the sector pack calls them.
_COMPONENT = re.compile(
    r"(?:^|[^a-z])(orders?|customers?|units?|qty|quantity|items?|lines?|transactions?|price|volume)(?:[^a-z]|$)",
    re.IGNORECASE,
)
_AMOUNT_NAME = re.compile(
    r"(?:^|[^a-z])(revenue|sales|turnover|income|amount|cost|expense|profit|margin)(?:[^a-z]|$)",
    re.IGNORECASE,
)
_TIME_NAME = re.compile(
    r"^(?:fiscal[_ ]?|financial[_ ]?)?(year|quarter|qtr|month|week|day|period|date|fy)$",
    re.IGNORECASE,
)


def _is_money(column: str, roles: Mapping[str, str]) -> bool:
    return roles.get(column) in _MONEY or bool(_AMOUNT_NAME.search(column))


def _is_component(column: str, roles: Mapping[str, str]) -> bool:
    return roles.get(column) in _VOLUME or bool(_COMPONENT.search(column))


def time_label(column: str, time_column: str | None, time_like: bool) -> bool:
    """A time column or a quarter/month/year label: a position in time, not a measure."""
    return column == time_column or time_like or bool(_TIME_NAME.match(column.strip()))


def redundant_correlation(
    x: str,
    y: str,
    roles: Mapping[str, str],
    *,
    time_column: str | None,
    time_like: Mapping[str, bool],
) -> tuple[str, str] | None:
    """(reason code, reason) when a correlation between x and y is not worth testing."""
    for column in (x, y):
        if time_label(column, time_column, bool(time_like.get(column))):
            return (
                "time_label",
                f"{column} is a position in time, not a measure; ask for a trend or a seasonal "
                "pattern instead",
            )
    if roles.get(x) in _MONEY and roles.get(y) in _MONEY:
        return "bookkeeping", f"{x} and {y} are built from each other (profit = amount - cost)"
    for a, b in ((x, y), (y, x)):
        if _is_money(a, roles) and _is_component(b, roles):
            return (
                "bookkeeping",
                f"{b} is one of the things {a} is made of, so a relation between them restates "
                "how the table is built",
            )
    return None
