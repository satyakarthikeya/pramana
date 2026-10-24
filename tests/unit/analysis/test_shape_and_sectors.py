"""Dataset shape and sector detection (PLAN §4.1, §14): deterministic, no model call."""

from __future__ import annotations

import pandas as pd
import pytest

from pramana.analysis import infer_schema, load_config
from pramana.analysis.sectors import detect_sector, load_packs
from pramana.analysis.shape import DataShape, classify_shape
from tests.unit.analysis import computed_fixtures as fx


def _schema(frame: pd.DataFrame):
    return infer_schema(frame, load_config().schema_inference)


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        (fx.cross_section, DataShape.CROSS_SECTION),
        (fx.time_series, DataShape.TIME_SERIES),
        (fx.finance_year, DataShape.PANEL),
        (fx.transactions, DataShape.TRANSACTIONS),
        (fx.health_sample, DataShape.CROSS_SECTION),
    ],
)
def test_shape_of_known_tables(build, expected) -> None:
    frame = build()
    assert classify_shape(frame, _schema(frame)).shape is expected


def test_panel_names_its_time_and_entity_columns() -> None:
    frame = fx.finance_year()
    shape = classify_shape(frame, _schema(frame))
    assert shape.time_column == "month"
    assert shape.entity_column == "region"
    assert shape.period == "month"
    assert shape.n_periods == 12
    assert shape.reasons


def test_one_financial_year_is_flagged_as_short() -> None:
    frame = fx.finance_year()
    shape = classify_shape(frame, _schema(frame))
    assert shape.full_cycles == 1


def test_finance_table_is_detected_as_finance() -> None:
    frame = fx.finance_year()
    match = detect_sector(list(frame.columns), load_packs())
    assert match.sector == "finance"
    assert match.roles["revenue"] == "amount"
    assert match.roles["cost"] == "cost"
    assert match.roles["profit"] == "profit"
    assert match.roles["region"] == "entity"


def test_nhanes_table_is_detected_as_health_through_the_codebook() -> None:
    frame = fx.health_sample()
    match = detect_sector(list(frame.columns), load_packs())
    assert match.sector == "health"
    assert match.roles["BMXBMI"] == "bmi"
    assert match.roles["WTMEC2YR"] == "survey_weight"
    assert match.roles["RIAGENDR"] == "sex"


def test_unrecognised_table_falls_back_to_general() -> None:
    match = detect_sector(["a", "b", "c"], load_packs())
    assert match.sector == "general"
    assert match.roles == {}


def test_user_override_wins_over_detection() -> None:
    frame = fx.finance_year()
    match = detect_sector(list(frame.columns), load_packs(), override="health")
    assert match.sector == "health"
    assert "override" in " ".join(match.reasons)


def test_unknown_override_is_refused() -> None:
    with pytest.raises(ValueError):
        detect_sector(["a"], load_packs(), override="astrology")


def test_packs_are_data_only() -> None:
    packs = load_packs()
    assert {"finance", "health"} <= set(packs)
    for pack in packs.values():
        assert pack.label and pack.roles
