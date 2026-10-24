"""The planted-fact recall script: the report surfaces every planted fact (regression net).

The tables are synthetic and seeded; this shows the report surfaces KNOWN facts, not that
it finds unknown ones. Baseline before the analyst layer was 3 of 7.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "calibration" / "analyst_recall.py"


def _load():
    spec = importlib.util.spec_from_file_location("analyst_recall", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_planted_fact_is_in_the_lead_findings() -> None:
    card = _load().score()
    missed = [(r["table"], name) for r in card["rows"] for name, ok in r["facts"].items() if not ok]
    assert not missed, missed
    assert card["lead_items_per_report"] <= 8
