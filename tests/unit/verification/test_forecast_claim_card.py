"""The forecast report card script: plumbing at a handful of replicates, not calibration.

The numbers come from running the script with 200 replicates per cell
(docs/evidence/FORECAST_CLAIM_2026-10-25.md). Here: it runs, its in-process path agrees with
the real gateway on the same series, and its planted shapes behave the way they are named.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "calibration" / "forecast_claim_card.py"


def _load():
    spec = importlib.util.spec_from_file_location("forecast_claim_card", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_replicate_of_each_cheap_shape_runs_and_summarises() -> None:
    card = _load()
    card._init(199)
    records = [card.replicate(("h1only", 60, rep, 7, 2)) for rep in range(4)]
    assert {r["status"] for r in records} == {"tested"}
    summary = card.summarize(records)
    assert summary["reps"] == 4 and summary["tested"] == 4
    assert "h1only" in card.render({"h1only|60|2": summary}, 199, 0.05)


def test_a_thirty_six_month_series_is_not_testable_at_two_periods_ahead() -> None:
    card = _load()
    card._init(199)
    record = card.replicate(("true", 36, 0, 7, 2))
    assert record["status"] == "not_testable" and "too few backtest origins" in record["reason"]


def test_the_planted_shapes_are_what_they_are_named() -> None:
    card = _load()
    rng = np.random.default_rng(0)
    broken = card.generate("break", 60, rng)
    assert broken[40:].mean() - broken[:20].mean() > 15  # growth plus the shift
    assert card.wilson(0, 200)[0] == 0.0 and 0.0 < card.wilson(10, 200)[0] < 0.05
