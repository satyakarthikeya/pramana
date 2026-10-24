"""E2: does Benjamini-Hochberg control false discoveries when claims share columns?

Design, metrics and the "bad result" line are in docs/evidence/CORRELATED_FDR_2026-10-25.md
and were written before the first run. This script only measures: it reads the repo's
`apply_bh` and the vetted permutation test and changes nothing.

Each replicate draws one table from a known covariance (every claimed pair is either exactly
uncorrelated or planted), builds m claims that share columns (star, chain, block), takes one
permutation p-value per claim from `pramana.verification.stats.permutation_test`, then applies
BH (repo), Holm and BY to the SAME p-values. The statistic is a dot product of standardised
ranks (Spearman up to a constant) because `spearman_rho` is ~50x slower per permutation;
the shuffling, add-one p-value and seeding are the library's. Permutations are REDUCED
(default 1000, the shipped config uses 10000).

    python scripts/calibration/eval_correlated_fdr.py --reps 1000 --out artifacts/e2.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats as sps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pramana.verification.config import load_config  # noqa: E402
from pramana.verification.fdr import apply_bh, bh_rejections  # noqa: E402
from pramana.verification.stats import permutation_test  # noqa: E402

N_ROWS = 150
BETA = 0.35
MASTER_SEED = 20261025
METHODS = ("bh", "holm", "by")
RHOS = (0.0, 0.3, 0.6, 0.9)
SIZES = (8, 24, 40)
FRACTIONS = (0.0, 0.25, 0.5)
#: m -> (outcomes, predictors, block size) for the bipartite "block" structure.
BLOCK_SHAPE = {8: (2, 4, 2), 24: (4, 6, 3), 40: (4, 10, 5)}


def all_cells() -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for structure in ("star", "block"):
        for rho, m, frac in itertools.product(RHOS, SIZES, FRACTIONS):
            cells.append({"structure": structure, "rho": rho, "m": m, "frac": frac})
    for m, frac in itertools.product(SIZES, FRACTIONS):
        cells.append({"structure": "chain", "rho": None, "m": m, "frac": frac})
    for index, cell in enumerate(cells):
        cell["id"] = index
    return cells


# --- tables with a known truth -------------------------------------------------


def _equicorrelated(size: int, rho: float) -> np.ndarray:
    return np.full((size, size), rho) + (1.0 - rho) * np.eye(size)


def _shrink_to_positive_definite(
    sigma: np.ndarray, entries: list[tuple[int, int]], beta: float
) -> tuple[np.ndarray, float]:
    """Scale the planted entries down until the matrix has a safe smallest eigenvalue."""
    scale = 1.0
    while True:
        trial = sigma.copy()
        for i, j in entries:
            trial[i, j] = trial[j, i] = beta * scale
        if np.linalg.eigvalsh(trial).min() > 0.02:
            return trial, beta * scale
        scale *= 0.95


def _draw(sigma: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    return rng.standard_normal((N_ROWS, sigma.shape[0])) @ np.linalg.cholesky(sigma).T


def draw_table(
    cell: dict[str, Any], rng: np.random.Generator
) -> tuple[np.ndarray, list[tuple[int, int]], list[bool], float, np.ndarray]:
    """(table, claims, truth, realised beta, covariance).

    Guarantees every claimed pair that is not planted has covariance exactly 0.
    """
    m, frac, rho = cell["m"], cell["frac"], cell["rho"]
    k = int(round(frac * m))
    if cell["structure"] == "star":
        # column 0 = outcome; 1..k = true predictors (block T); k+1..m = null predictors (N)
        sigma = np.eye(m + 1)
        if k:
            sigma[1 : k + 1, 1 : k + 1] = _equicorrelated(k, rho)
        if m - k:
            sigma[k + 1 :, k + 1 :] = _equicorrelated(m - k, rho)
        planted = [(0, j) for j in range(1, k + 1)]
        sigma, beta = _shrink_to_positive_definite(sigma, planted, BETA)
        claims = [(0, j) for j in range(1, m + 1)]
        truth = [j <= k for j in range(1, m + 1)]
        return _draw(sigma, rng), claims, truth, beta, sigma
    if cell["structure"] == "block":
        n_out, n_pred, size = BLOCK_SHAPE[m]
        n_blocks = n_pred // size
        sigma = np.eye(n_out + n_pred)
        for b in range(n_blocks):
            lo = n_out + b * size
            sigma[lo : lo + size, lo : lo + size] = _equicorrelated(size, rho)
        grid = [(a, b) for a in range(n_out) for b in range(n_blocks)]
        chosen = rng.choice(len(grid), size=int(round(frac * len(grid))), replace=False)
        true_cells = {grid[int(i)] for i in chosen}
        planted = [(a, n_out + b * size + t) for (a, b) in true_cells for t in range(size)]
        sigma, beta = _shrink_to_positive_definite(sigma, planted, BETA)
        claims, truth = [], []
        for a in range(n_out):
            for b in range(n_blocks):
                for t in range(size):
                    claims.append((a, n_out + b * size + t))
                    truth.append((a, b) in true_cells)
        return _draw(sigma, rng), claims, truth, beta, sigma
    # chain: c_{i+1} = r_i c_i + sqrt(1 - r_i^2) e_i; r_i = BETA on true edges, else 0
    edges = set(rng.choice(m, size=k, replace=False).tolist())
    cols = [rng.standard_normal(N_ROWS)]
    for i in range(m):
        r = BETA if i in edges else 0.0
        cols.append(r * cols[-1] + math.sqrt(1 - r * r) * rng.standard_normal(N_ROWS))
    claims = [(i, i + 1) for i in range(m)]
    truth = [i in edges for i in range(m)]
    sigma = np.eye(m + 1)
    for i in edges:
        sigma[i, i + 1] = sigma[i + 1, i] = BETA
    return np.column_stack(cols), claims, truth, BETA, sigma


def standardised_ranks(table: np.ndarray) -> np.ndarray:
    ranks = sps.rankdata(table, axis=0)
    return (ranks - ranks.mean(axis=0)) / ranks.std(axis=0)


# --- corrections ------------------------------------------------------------------


def holm_rejections(p: np.ndarray, alpha: float) -> np.ndarray:
    """Holm step-down, strict `<` like the repo's gate: stop at the first failure."""
    order = np.argsort(p, kind="stable")
    m = p.size
    out = np.zeros(m, dtype=bool)
    for rank, index in enumerate(order):
        if p[index] < alpha / (m - rank):
            out[index] = True
        else:
            break
    return out


def by_rejections(p: np.ndarray, alpha: float) -> np.ndarray:
    """Benjamini-Yekutieli: the repo's BH q-values times the harmonic number H_m."""
    harmonic = float(np.sum(1.0 / np.arange(1, p.size + 1)))
    q = np.minimum(np.asarray(apply_bh(p, alpha)) * harmonic, 1.0)
    return q < alpha


def simulate_replicate(args: tuple[dict[str, Any], int, int, float, int]) -> dict[str, Any]:
    cell, rep, n_permutations, alpha, seed = args
    rng = np.random.default_rng(np.random.SeedSequence([seed, cell["id"], rep]))
    table, claims, truth_list, beta, sigma = draw_table(cell, rng)
    truth = np.asarray(truth_list, dtype=bool)
    for (i, j), is_true in zip(claims, truth, strict=True):  # the generator's own promise
        assert (sigma[i, j] != 0.0) == bool(is_true)
    z = standardised_ranks(table)
    p = np.empty(len(claims))
    for index, (i, j) in enumerate(claims):
        result = permutation_test(
            z[:, i],
            z[:, j],
            lambda a, b: float(a @ b) / N_ROWS,
            n_permutations=n_permutations,
            seed=int(rng.integers(2**31 - 1)),
        )
        p[index] = result.p_value
    q = apply_bh(p, alpha)
    rejected = {
        "bh": np.asarray(bh_rejections(q, alpha)),
        "holm": holm_rejections(p, alpha),
        "by": by_rejections(p, alpha),
    }
    row: dict[str, Any] = {"cell": cell["id"], "n_true": int(truth.sum()), "beta": beta}
    for name, rej in rejected.items():
        row[name] = (int((rej & ~truth).sum()), int(rej.sum()), int((rej & truth).sum()))
    return row


# --- aggregation ------------------------------------------------------------------


def summarise(rows: list[dict[str, Any]], cell: dict[str, Any]) -> dict[str, Any]:
    reps = len(rows)
    out: dict[str, Any] = {
        **cell,
        "reps": reps,
        "true_fraction_realised": float(np.mean([r["n_true"] for r in rows])) / cell["m"],
        "beta_mean": float(np.mean([r["beta"] for r in rows])),
    }
    for name in METHODS:
        v = np.array([r[name][0] for r in rows], dtype=float)
        rej = np.array([r[name][1] for r in rows], dtype=float)
        hit = np.array([r[name][2] for r in rows], dtype=float)
        n_true = np.array([r["n_true"] for r in rows], dtype=float)
        fdp = v / np.maximum(rej, 1.0)
        fdr = float(fdp.mean())
        se = float(fdp.std(ddof=1) / math.sqrt(reps)) if reps > 1 else float("nan")
        any_false = int((v >= 1).sum())
        ci = sps.binomtest(any_false, reps).proportion_ci(confidence_level=0.95, method="wilson")
        fwer = any_false / reps
        out[name] = {
            "fdr": fdr,
            "fdr_se": se,
            "fdr_lo": fdr - 1.96 * se,
            "fdr_hi": fdr + 1.96 * se,
            "fwer": fwer,
            "fwer_se": math.sqrt(fwer * (1 - fwer) / reps),
            "fwer_lo": float(ci.low),
            "fwer_hi": float(ci.high),
            "power": float(hit.sum() / n_true.sum()) if n_true.sum() else None,
            "mean_rejections": float(rej.mean()),
        }
    if cell["frac"] == 0.0:  # all null: FDP is the any-false indicator, so FDR == FWER
        for name in METHODS:
            assert abs(out[name]["fdr"] - out[name]["fwer"]) < 1e-12
    return out


def run_study(
    reps: int,
    n_permutations: int = 1000,
    workers: int = 1,
    cells: list[dict[str, Any]] | None = None,
    seed: int = MASTER_SEED,
    alpha: float | None = None,
) -> dict[str, Any]:
    alpha = load_config().statistics.alpha if alpha is None else alpha
    cells = all_cells() if cells is None else cells
    jobs = [(cell, rep, n_permutations, alpha, seed) for cell in cells for rep in range(reps)]
    started = time.time()
    if workers > 1:
        with Pool(workers) as pool:
            results = pool.map(
                simulate_replicate, jobs, chunksize=max(1, len(jobs) // (workers * 16))
            )
    else:
        results = [simulate_replicate(job) for job in jobs]
    by_cell: dict[int, list[dict[str, Any]]] = {}
    for row in results:
        by_cell.setdefault(row["cell"], []).append(row)
    return {
        "alpha": alpha,
        "reps": reps,
        "n_permutations": n_permutations,
        "n_rows": N_ROWS,
        "beta_target": BETA,
        "seed": seed,
        "seconds": time.time() - started,
        "note": "permutations reduced from the configured value for runtime",
        "cells": [summarise(by_cell[c["id"]], c) for c in cells],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--reps", type=int, default=500)
    parser.add_argument("--permutations", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=MASTER_SEED)
    parser.add_argument("--out", type=Path, default=Path("artifacts/e2.json"))
    args = parser.parse_args()
    result = run_study(args.reps, args.permutations, args.workers, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"wrote {args.out} in {result['seconds']:.0f}s")


if __name__ == "__main__":
    main()
