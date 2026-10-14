"""READ-ONLY: measure the gating effect of every candidate pair on the demo frame.

    .venv/Scripts/python.exe scripts/calibration/measure_effects.py \
        [--csv data/demo/nhanes_demo.csv] [--permutations 2000]

For each candidate the real analysis step proposes, this computes the SAME gating
metric the template generator would use (spearman_rho / kendall_tau_b / cliffs_delta /
epsilon_squared, all from `pramana.verification.stats`) plus a permutation p with the
configured seed. It changes nothing: no config, no data, no files.

`--permutations` defaults to 2000 (the shipped config uses 10000) purely for speed.
Effects do not depend on it; p-values only get coarser (floor 1/(B+1)), and the
decoy / nulls are far from that floor, so the table is unaffected for calibration.

Role labels: the two planted TRUE pairs and the injected DECOY come from
`benchmark.demo` in configs/analysis.yaml and demo_dataset.py; any other pair
with the moon-phase column is a "chance-null" (nonsense variable, n<=40). Everything
else is "unplanted-real": not planted, but a genuine NHANES association at n~1500, so
it is NOT a null and a floor is not expected to separate it from the planted truth.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pramana.analysis.handlers import analyze, ingest, prepare  # noqa: E402
from pramana.contracts.enums import ClaimType  # noqa: E402
from pramana.verification.config import load_config  # noqa: E402
from pramana.verification.stats import (  # noqa: E402
    cliffs_delta,
    epsilon_squared,
    kendall_tau_b,
    permutation_test,
    permutation_test_groups,
    spearman_rho,
)

TRUE_PAIRS = [{"age_years", "systolic_bp"}, {"bmi", "hdl_chol"}]
DECOY_PAIR = {"hba1c_pct", "birth_moon_phase_pct"}


def role(variables: list[str]) -> str:
    pair = set(variables)
    if pair in TRUE_PAIRS:
        return "TRUE"
    if pair == DECOY_PAIR:
        return "DECOY"
    if "birth_moon_phase_pct" in pair:
        return "chance-null"  # nonsense variable on a ~40-row pilot: no real relationship
    return "unplanted-real"  # not planted, but a genuine association at n~1500


def measure(candidate, frame: pd.DataFrame, n_perm: int, seed: int, min_obs: int):
    x_name, y_name = candidate.variables[0], candidate.variables[1]
    if candidate.claim_type in (ClaimType.CORRELATION, ClaimType.TREND):
        stat = spearman_rho if candidate.claim_type is ClaimType.CORRELATION else kendall_tau_b
        metric = (
            "spearman_rho" if candidate.claim_type is ClaimType.CORRELATION else "kendall_tau_b"
        )
        pair = frame[[x_name, y_name]].apply(pd.to_numeric, errors="coerce").dropna()
        res = permutation_test(
            pair[x_name].to_numpy(float),
            pair[y_name].to_numpy(float),
            stat,
            n_permutations=n_perm,
            seed=seed,
        )
        return metric, res.statistic, res.p_value, len(pair), float(abs(res.statistic))
    if candidate.claim_type is ClaimType.GROUP_DIFFERENCE:
        cols = frame[[x_name, y_name]].copy()
        cols[y_name] = pd.to_numeric(cols[y_name], errors="coerce")
        cols = cols.dropna()
        labels = sorted(cols[x_name].astype(str).unique().tolist())
        if candidate.reference_group in labels:
            labels = [candidate.reference_group] + [
                name for name in labels if name != candidate.reference_group
            ]
        groups = [
            cols.loc[cols[x_name].astype(str) == name, y_name].to_numpy(float) for name in labels
        ]
        if len(groups) == 2:
            res = permutation_test_groups(
                groups, lambda g: cliffs_delta(g[0], g[1]), n_permutations=n_perm, seed=seed
            )
            return "cliffs_delta", res.statistic, res.p_value, len(cols), float(abs(res.statistic))
        res = permutation_test_groups(
            groups, lambda g: epsilon_squared(list(g)), n_permutations=n_perm, seed=seed
        )
        return (
            "epsilon_squared",
            res.statistic,
            res.p_value,
            len(cols),
            float(np.sqrt(abs(res.statistic))),
        )
    return str(candidate.claim_type), float("nan"), float("nan"), 0, float("nan")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--csv", type=Path, default=REPO_ROOT / "data" / "demo" / "nhanes_demo.csv")
    parser.add_argument("--permutations", type=int, default=2000)
    args = parser.parse_args()

    import os

    os.environ.setdefault("PRAMANA_VERIFICATION_GENERATOR", "template")
    config = load_config()
    seed, min_obs = config.statistics.seed, config.statistics.min_observations

    loaded = ingest({"dataset_ref": str(args.csv)})
    prepared = prepare(loaded)
    candidates = analyze(prepared)["candidate_insights"]

    rows = []
    for candidate in candidates:
        metric, effect, p, n, gated = measure(
            candidate, prepared["dataset"], args.permutations, seed, min_obs
        )
        rows.append(
            (
                candidate.insight_id,
                " ~ ".join(candidate.variables),
                metric,
                effect,
                gated,
                p,
                n,
                role(candidate.variables),
            )
        )
    table = pd.DataFrame(
        rows, columns=["id", "pair", "metric", "effect", "gated_effect", "p", "n", "role"]
    )
    print(
        f"seed={seed}  permutations={args.permutations} "
        f"(config: {config.statistics.n_permutations})"
    )
    pd.set_option("display.width", 200, "display.max_rows", 200, "display.max_colwidth", 60)
    print(
        table.drop(columns="id")
        .sort_values(["metric", "gated_effect"], ascending=[True, False])
        .to_string(index=False, float_format=lambda v: f"{v:.4g}")
    )
    print("\nBy metric (gated effect = |effect|, or sqrt(eps^2) for epsilon_squared):")
    for metric, group in table.groupby("metric"):
        for r in ("TRUE", "DECOY", "chance-null", "unplanted-real"):
            sub = group[group["role"] == r]
            if len(sub):
                print(
                    f"  {metric:<16} {r:<5} n={len(sub):<3} gated min={sub.gated_effect.min():.3f} "
                    f"max={sub.gated_effect.max():.3f}"
                )


if __name__ == "__main__":
    main()
