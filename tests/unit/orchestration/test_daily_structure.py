"""A long daily table with one row per day reaches the gate as a daily time series."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pramana.analysis import infer_schema, load_config
from pramana.orchestration.analysis_integration import data_structure_for


def _structure(frame: pd.DataFrame):
    return data_structure_for(frame, infer_schema(frame, load_config().schema_inference))


def test_one_row_per_day_is_a_daily_time_series_not_transactions() -> None:
    rng = np.random.default_rng(1)
    n = 400
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2023-01-01", periods=n, freq="D"),
            "region": rng.choice(["north", "south", "east"], n),
            "sales": rng.normal(100, 10, n),
        }
    )
    structure = _structure(frame)
    assert structure.shape.value == "time_series" and structure.period == "day"
    assert structure.entity_column is None


def test_several_rows_per_day_stay_transactions() -> None:
    rng = np.random.default_rng(2)
    days = pd.date_range("2023-01-01", periods=300, freq="D").repeat(3)
    frame = pd.DataFrame(
        {"date": days, "store": rng.choice(list("ABCDEFGH"), len(days)),
         "sales": rng.normal(100, 10, len(days))}
    )
    assert _structure(frame).shape.value != "time_series"
