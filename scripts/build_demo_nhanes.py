"""Build data/demo_nhanes_small.csv from three NHANES 2017-2018 XPT modules.

Modules (downloaded from wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/):
    P_DEMO  demographics   -> RIDAGEYR (age, years), RIAGENDR (sex, 1=male 2=female)
    P_BMX   body measures  -> BMXBMI   (BMI, kg/m^2)
    P_GLU   glucose        -> LBXGLU   (fasting plasma glucose, mg/dL)

The output keeps only those four columns, drops rows with any null, samples
600 rows with a fixed seed, and adds two decoy columns:

  BMXBMI_SHUFFLED_DECOY   BMXBMI shuffled: same marginal distribution as BMI, no
                          association with anything. In-sample |rho| vs LBXGLU is
                          ~0.02, which is BELOW hypotheses.min_abs_correlation
                          (0.15), so the analysis module's pre-filter drops it
                          before a CandidateInsight exists. It never reaches the
                          gateway; the demo reports it as "not proposed".
  BIRTH_MOON_PHASE_PCT    P. Rohith's planted decoy (analysis/benchmark/
                          demo_dataset.inject_false_correlation): a nonsense
                          value present on only 40 rows, with an in-sample
                          Spearman rho of ~0.20 against LBXGLU on those rows.
                          That clears the pre-filter, so it IS proposed, and at
                          n=40 it is indistinguishable from chance, so the
                          gateway should REJECT it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pramana.analysis.benchmark.demo_dataset import (  # noqa: E402
    DemoSpec,
    inject_false_correlation,
)

SEED = 42
MAX_ROWS = 600
KEEP = ["RIDAGEYR", "RIAGENDR", "BMXBMI", "LBXGLU"]
SHUFFLED_DECOY = "BMXBMI_SHUFFLED_DECOY"

#: Same shape as the `benchmark.demo` block of configs/analysis.yaml, pointed at the
#: small frame. `n_rows`/`min_age_years` are required by the model but unused here
#: (the row sample is taken above); the decoy fields are what matter.
PILOT_DECOY_SPEC = DemoSpec(
    seed=SEED,
    n_rows=MAX_ROWS,
    min_age_years=0,
    decoy_column="BIRTH_MOON_PHASE_PCT",
    decoy_target="LBXGLU",
    decoy_pilot_rows=40,
    decoy_target_rho=0.20,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/nhanes"))
    parser.add_argument("--out", type=Path, default=Path("data/demo_nhanes_small.csv"))
    args = parser.parse_args()

    frames = [
        pd.read_sas(args.raw_dir / f"{module}.xpt", format="xport")
        for module in ("P_DEMO", "P_BMX", "P_GLU")
    ]
    merged = frames[0].merge(frames[1], on="SEQN").merge(frames[2], on="SEQN")
    print(f"merged on SEQN: {len(merged)} rows")

    subset = merged[KEEP].dropna()
    print(f"non-null in {KEEP}: {len(subset)} rows")

    if len(subset) > MAX_ROWS:
        subset = subset.sample(n=MAX_ROWS, random_state=SEED)
    subset = subset.reset_index(drop=True)

    rng = np.random.default_rng(SEED)
    subset[SHUFFLED_DECOY] = rng.permutation(subset["BMXBMI"].to_numpy())
    subset, planted = inject_false_correlation(subset, PILOT_DECOY_SPEC)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    subset.to_csv(args.out, index=False)
    print(f"wrote {args.out} ({len(subset)} rows, seed={SEED})")
    print(subset.describe().T[["count", "mean", "std", "min", "max"]])
    print("Spearman rho with LBXGLU (pairwise-complete):")
    print(subset.corr(method="spearman", numeric_only=True)["LBXGLU"].round(3))
    print(
        f"pilot decoy {planted.variables[1]}: planted rho {planted.in_sample_rho:+.3f} "
        f"on n={planted.n_observations}, expected {planted.expected_verdict}"
    )


if __name__ == "__main__":
    main()
