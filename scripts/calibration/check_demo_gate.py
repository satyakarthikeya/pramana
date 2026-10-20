"""Run the demo frame through the real gateway (template generator) and print verdicts.

    .venv/Scripts/python.exe scripts/calibration/check_demo_gate.py \
        [--csv data/demo/nhanes_demo.csv] [--permutations 10000]

Candidates come from the real analysis step; verification is `verify_batch` with the
shipped config pinned to the offline template generator via `model_copy` (no env var,
no API key, no network). Thresholds are the shipped ones. Read-only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "calibration"))

from measure_effects import role  # noqa: E402

from pramana.analysis.handlers import analyze, ingest, prepare  # noqa: E402
from pramana.verification.config import VerificationConfig, load_config  # noqa: E402
from pramana.verification.gateway import verify_batch  # noqa: E402


def pinned_config(n_permutations: int | None) -> VerificationConfig:
    shipped = load_config()
    config = shipped.model_copy(
        update={"llm": shipped.llm.model_copy(update={"generator": "template"})}
    )
    if n_permutations is not None:
        config = config.model_copy(
            update={
                "statistics": config.statistics.model_copy(
                    update={"n_permutations": n_permutations}
                )
            }
        )
    return config


def gate_frame_path(csv: Path, config: VerificationConfig):
    prepared = prepare(ingest({"dataset_ref": str(csv)}))
    candidates = analyze(prepared)["candidate_insights"]
    proofs = verify_batch(candidates, prepared["dataset"], config)
    return candidates, proofs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--csv", type=Path, default=REPO_ROOT / "data" / "demo" / "nhanes_demo.csv")
    parser.add_argument("--permutations", type=int, default=None, help="default: shipped config")
    args = parser.parse_args()

    config = pinned_config(args.permutations)
    candidates, proofs = gate_frame_path(args.csv, config)
    print(
        f"generator={config.llm.generator} permutations={config.statistics.n_permutations} "
        f"alpha={config.statistics.alpha} candidates={len(candidates)}"
    )
    print(
        f"{'role':<15} {'pair':<46} {'verdict':<7} {'outcome':<12} "
        f"{'p':>9} {'q':>9} {'effect':>8}  metric"
    )
    order = {"TRUE": 0, "DECOY": 1, "chance-null": 2, "unplanted-real": 3}
    rows = sorted(zip(candidates, proofs, strict=True), key=lambda cp: order[role(cp[0].variables)])
    for candidate, proof in rows:
        f = lambda v, s: "-" if v is None else format(v, s)  # noqa: E731
        print(
            f"{role(candidate.variables):<15} {' ~ '.join(candidate.variables):<46} "
            f"{proof.verdict.value:<7} {proof.gate_outcome.value:<12} {f(proof.p_value, '.3g'):>9} "
            f"{f(proof.q_value, '.3g'):>9} {f(proof.effect_size, '+.3f'):>8}  "
            f"{proof.effect_metric.value if proof.effect_metric else '-'}"
        )
    passed = sum(p.verdict.value == "PASS" for p in proofs)
    print(f"\n{passed} PASS, {len(proofs) - passed} REJECT")


if __name__ == "__main__":
    main()
