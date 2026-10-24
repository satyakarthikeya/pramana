"""F2: a short monthly series still leaves the gate enough periods to test a trend."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.contracts import DataStructure, TableShape
from pramana.verification.config import load_config
from pramana.verification.schemes import split_rows


def _series(n_months: int) -> tuple[pd.DataFrame, DataStructure]:
    frame = pd.DataFrame(
        {
            "month": pd.date_range("2022-04-01", periods=n_months, freq="MS").astype(str),
            "revenue": np.arange(n_months, dtype=float),
        }
    )
    structure = DataStructure(
        shape=TableShape.TIME_SERIES,
        time_column="month",
        period="month",
        declared_by="caller",
    )
    return frame, structure


@pytest.mark.parametrize(
    ("months", "confirm_periods"),
    [
        (36, 20),  # half would be 18, under the 20 a trend needs: hold back 20, explore 16
        (60, 30),  # half already reaches the minimum: unchanged
        (24, 12),  # holding back 20 would leave 4 to explore (< 8): keep the half
    ],
)
def test_confirmation_reaches_the_trend_minimum_when_exploration_can_spare_it(
    months: int, confirm_periods: int
) -> None:
    config = load_config()
    frame, structure = _series(months)
    explore, confirm, record = split_rows(frame, structure, config)
    assert record.method == "by_time"
    assert len(confirm) == confirm_periods
    assert set(explore).isdisjoint(confirm) and len(explore) + len(confirm) == months
    assert confirm.min() > explore.max()  # later periods confirm
    assert record.confirmation_fraction == pytest.approx(confirm_periods / months)
    if months - confirm_periods >= config.dependence.min_exploration_periods:
        assert len(explore) >= config.dependence.min_exploration_periods
