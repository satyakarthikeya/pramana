"""Plumbing test for the E1 gate-versus-no-gate script (scripts/calibration/eval_gate_ablation.py).

Tiny K, few permutations: it checks that the tables are what the doc says, that every arm
returns the same scoring fields, and that the aggregation runs. It does NOT check any
statistical property; the real numbers come from the full run.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "calibration" / "eval_gate_ablation.py"


@pytest.fixture(scope="module")
def e1():
    spec = importlib.util.spec_from_file_location("eval_gate_ablation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["eval_gate_ablation"] = module
    spec.loader.exec_module(module)
    return module


def test_tables_have_the_documented_shape(e1) -> None:
    seen = set()
    for k in range(27):
        spec = e1.table_spec(k)
        frame, claims, truth = e1.make_table(spec)
        seen.add((spec["structure"], spec["rho"], spec["n_true"]))
        assert len(claims) == 12
        assert len(truth) == spec["n_true"]
        assert truth <= {c.insight_id for c in claims}
        for claim in claims:
            assert set(claim.variables) <= set(frame.columns)
    assert len(seen) == 27  # the balanced cycle covers every cell


def test_tables_are_reproducible(e1) -> None:
    a, _, ta = e1.make_table(e1.table_spec(4))
    b, _, tb = e1.make_table(e1.table_spec(4))
    assert a.equals(b) and ta == tb


def test_naive_arm_reports_more_than_it_should_on_a_seasonal_table(e1) -> None:
    spec = e1.table_spec(1)  # season structure
    assert spec["structure"] == "season"
    frame, claims, truth = e1.make_table(spec)
    reported = e1.naive_reports(frame, claims, 0.05)
    assert len(reported - truth) >= 1  # the shared season makes null pairs look related


def test_end_to_end_two_tables_and_aggregate(e1) -> None:
    rows = [e1.run_table((e1.table_spec(k), 200, False)) for k in (0, 2)]
    for row in rows:
        assert not row["errors"], row["errors"]
        assert set(row["arms"]) == set(e1.ARMS)
        for arm in row["arms"].values():
            assert {"reported", "false", "true_kept", "n_true", "seconds"} <= set(arm)
            assert 0 <= arm["false"] <= arm["reported"]
        # same proofs, later stages only remove: C is within B+, which is within B
        assert row["arms"]["C_full_gate"]["reported"] <= row["arms"]["Bplus_bh_floor"]["reported"]
        assert row["arms"]["Bplus_bh_floor"]["reported"] <= row["arms"]["B_bh_only"]["reported"]
    agg = e1.aggregate(rows)
    assert set(agg["overall"]) == set(e1.ARMS)
    assert "A_naive" in e1.render(agg)
