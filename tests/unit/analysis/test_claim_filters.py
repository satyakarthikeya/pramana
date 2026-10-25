"""Bookkeeping and time-label claims are dropped before the gate, with a reason."""

from __future__ import annotations

import pytest

from pramana.analysis.claim_filters import redundant_correlation

ROLES = {
    "revenue": "amount",
    "cost": "cost",
    "units_sold": "quantity",
    "orders": "quantity",
    "region": "entity",
}


def _check(x: str, y: str, **kw):
    return redundant_correlation(
        x, y, ROLES, time_column=kw.get("time"), time_like=kw.get("like", {})
    )


@pytest.mark.parametrize(
    ("x", "y"),
    [
        ("revenue", "orders"),
        ("orders", "revenue"),
        ("revenue", "units_sold"),
        ("revenue", "cost"),
        ("revenue", "customers"),
        ("avg_unit_price", "revenue"),
    ],
)
def test_a_money_column_against_what_it_is_made_of_is_bookkeeping(x: str, y: str) -> None:
    result = _check(x, y)
    assert result is not None and result[0] == "bookkeeping"


@pytest.mark.parametrize("label", ["quarter", "month", "fiscal_year", "Year"])
def test_a_time_label_is_never_a_variable_in_an_association(label: str) -> None:
    result = _check(label, "revenue")
    assert result is not None and result[0] == "time_label"


def test_the_time_column_itself_is_a_time_label() -> None:
    assert _check("invoice_date", "revenue", time="invoice_date")[0] == "time_label"


@pytest.mark.parametrize(
    ("x", "y"), [("revenue", "age"), ("discount_rate", "margin_pct"), ("tenure", "churn_rate")]
)
def test_a_genuine_pair_is_left_alone(x: str, y: str) -> None:
    assert _check(x, y) is None
