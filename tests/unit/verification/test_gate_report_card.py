"""S2: the report card script runs end to end and reports sane rates.

This checks the plumbing at a handful of replicates, not calibration. The calibration
numbers come from running the script with many replicates (see the design doc); the
per-scheme size tests live in test_dependence.py and test_valid_nulls_gateway.py.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np

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
    chosen = module.SCENARIOS[:1] + module.SCENARIOS[4:5]
    rows = {s[0]: module.run_scenario(*s, 12, config, 7) for s in chosen}
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


# --- v2 rows: correlated families and per-attack kill / survive rates ------------------


def test_wilson_interval_known_answers() -> None:
    module = _load()
    lo, hi = module.wilson(0, 100)
    assert lo == 0.0 and 0.03 < hi < 0.04  # rule-of-three territory
    lo, hi = module.wilson(50, 100)
    assert abs((lo + hi) / 2 - 0.5) < 1e-9 and 0.40 < lo < 0.41
    assert all(math.isnan(v) for v in module.wilson(0, 0))


def test_planted_shapes_are_null_when_rho_is_zero_and_related_when_it_is_not() -> None:
    from scipy.stats import spearmanr

    module = _load()
    rng = np.random.default_rng(11)
    for shape in module.SHAPES:
        for rho, related in ((0.0, False), (0.3, True)):
            frame = module.shape_table(shape, rng, 300, rho)
            a, b = (np.diff(frame["x"]), np.diff(frame["y"])) if shape == "series" else (
                frame["x"], frame["y"])
            p = spearmanr(a, b)[1]
            assert (p < 0.01) if related else (p > 0.001), (shape, rho, p)


def test_attack_cell_counts_are_consistent_for_both_a2_rules() -> None:
    module = _load()
    cell = module.attack_cell(("gaussian", 120, 0.3, 3, 5, 40, 200, ("point", "interval")))
    assert cell["cleared"] == 3 and cell["attempts"] >= 3
    for rule in ("point", "interval"):
        acc = cell["rules"][rule]
        assert set(acc["broken"]) == set(module.ATTACK_IDS)
        assert 0 <= acc["any_broken"] <= cell["cleared"]
        assert all(0 <= v <= cell["cleared"] for v in acc["broken"].values())
    # only A2 differs between the rules: every other attack is identical on the same tables
    for a in module.ATTACK_IDS:
        if a != "A2":
            assert cell["rules"]["point"]["broken"][a] == cell["rules"]["interval"]["broken"][a]
    assert cell["rules"]["point"]["a2_too_noisy"] == 0  # the third state exists only on `interval`


def test_attack_cell_null_cells_stop_at_the_attempt_cap() -> None:
    module = _load()
    cell = module.attack_cell(("gaussian", 60, 0.0, 50, 2, 3, 200, ("point", "interval")))
    assert cell["attempts"] <= 150 and cell["cleared"] < 50


def test_pooled_attack_rows_and_markdown_render() -> None:
    module = _load()
    cells = module.attack_card_v2(2, workers=1, cells=[("gaussian", 60, 0.3), ("series", 60, 0.3)])
    pooled = module.pooled_attack_rows(cells)
    assert {(r["kind"], r["a2_rule"]) for r in pooled} == {("true", "point"), ("true", "interval"),
                                                          ("null", "point"), ("null", "interval")}
    assert "| true effect | gaussian | 60 |" in module.render_attack_v2(cells)


def test_family_summary_reports_standard_errors_and_a_wilson_interval() -> None:
    module = _load()
    truth = [True, False, False]
    stages = ("none", "bh", "holm", "pass")
    reps = [{"truth": truth, "arms": {a: [True, True, False] for a in stages},
             "attack_broken": [False] * 3},
            {"truth": truth, "arms": {a: [True, False, False] for a in stages},
             "attack_broken": [False] * 3}]
    rows = module.summarise_family("toy", 1, reps)
    bh = next(r for r in rows if r["arm"] == "bh")
    assert bh["fdp"] == 0.25 and bh["any_false_pass"] == 0.5 and bh["power"] == 1.0
    assert bh["fdp_se"] > 0 and bh["any_false_lo"] < 0.5 < bh["any_false_hi"]


def test_family_replicate_runs_the_real_gateway_on_eight_claims() -> None:
    module = _load()
    out = module.family_replicate((3, 100, 0.3, 3, True, 200, 200, 0))
    assert len(out["truth"]) == 8 and sum(out["truth"]) == 3
    assert set(out["arms"]) == {"none", "bh", "holm", "pass"}
    assert all(len(v) == 8 for v in out["arms"].values())
    # a final PASS is always BH-significant: the attacks and the floor can only remove claims
    assert all(b or not p for p, b in zip(out["arms"]["pass"], out["arms"]["bh"], strict=True))
