"""E2 script plumbing: tiny replicates; checks structure and the generator's truth only."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "calibration" / "eval_correlated_fdr.py"


def _load():
    spec = importlib.util.spec_from_file_location("eval_correlated_fdr", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_structure_runs_and_reports_consistent_numbers() -> None:
    module = _load()
    picked = [
        c
        for c in module.all_cells()
        if c["m"] == 8 and c["frac"] in (0.0, 0.5) and c["rho"] in (None, 0.6)
    ]
    assert {c["structure"] for c in picked} == {"star", "chain", "block"}
    result = module.run_study(reps=3, n_permutations=99, workers=1, cells=picked)
    assert len(result["cells"]) == len(picked)
    for cell in result["cells"]:
        assert cell["reps"] == 3
        for name in module.METHODS:
            assert 0.0 <= cell[name]["fdr"] <= 1.0 and 0.0 <= cell[name]["fwer"] <= 1.0
            assert cell[name]["fdr"] <= cell[name]["fwer"] + 1e-12
        assert abs(cell["true_fraction_realised"] - cell["frac"]) < 1e-9


def test_planted_pairs_are_the_only_correlated_claims() -> None:
    module = _load()
    rng = np.random.default_rng(1)
    for cell in module.all_cells()[::7]:
        _, claims, truth, beta, sigma = module.draw_table(cell, rng)
        assert 0 < beta <= module.BETA and len(claims) == cell["m"]
        assert all((sigma[i, j] != 0.0) == t for (i, j), t in zip(claims, truth, strict=True))


def test_holm_and_by_are_never_looser_than_bh() -> None:
    module = _load()
    p = np.array([0.001, 0.004, 0.02, 0.03, 0.2, 0.5, 0.7, 0.9])
    bh = np.asarray(module.bh_rejections(module.apply_bh(p, 0.05), 0.05))
    assert module.by_rejections(p, 0.05).sum() <= bh.sum()
    assert module.holm_rejections(p, 0.05).sum() <= bh.sum()
