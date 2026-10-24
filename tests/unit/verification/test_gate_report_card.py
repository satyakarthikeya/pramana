"""S2: the report card script runs end to end and reports sane rates.

This checks the plumbing at a handful of replicates, not calibration. The calibration
numbers come from running the script with many replicates (see the design doc); the
per-scheme size tests live in test_dependence.py and test_valid_nulls_gateway.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "calibration" / "gate_report_card.py"


def _load():
    spec = importlib.util.spec_from_file_location("gate_report_card", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_report_card_assigns_the_intended_scheme_to_every_scenario() -> None:
    card = _load().report_card(reps=3)
    gate_rows = [r for r in card["rows"] if r["kind"] in ("false_positive", "power")]
    assert len(gate_rows) == 6
    assert all(r["assigned_wrong_scheme"] == 0 for r in gate_rows), gate_rows
    assert all(0.0 <= r["rate_q_below_alpha"] <= 1.0 for r in gate_rows)
    kill = [r for r in card["rows"] if r["kind"] == "false_kill"]
    assert len(kill) == 1 and 0.0 <= kill[0]["rate_any_attack_broken"] <= 1.0


def test_the_planted_strong_effect_is_found_far_more_often_than_a_null_is() -> None:
    module = _load()
    config = module.pinned_config()
    rows = {s[0]: module.run_scenario(*s, 12, config, 7) for s in module.SCENARIOS[:1] + module.SCENARIOS[4:5]}
    null = rows["null: independent rows"]["rate_q_below_alpha"]
    power = rows["power: rho about 0.3, 100 rows"]["rate_q_below_alpha"]
    assert power > null + 0.3


def test_the_extra_card_reports_family_and_attack_rows() -> None:
    module = _load()
    family = module.family_card(reps=2, n_permutations=200)
    assert {r["arm"] for r in family} == {"none", "bh", "holm"}
    assert all(0.0 <= r["any_false_pass"] <= 1.0 for r in family)
    attacks = module.attack_card(reps=3)
    assert {r["a2_rule"] for r in attacks} == {"point", "interval"}
    assert all(0.0 <= r["share_broken"] <= 1.0 for r in attacks)
