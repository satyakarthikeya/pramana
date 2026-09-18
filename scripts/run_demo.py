"""Run PRAMANA end to end on the NHANES demo dataset and print what happened.

    .venv/Scripts/python.exe scripts/run_demo.py            # Windows
    .venv/bin/python scripts/run_demo.py                    # POSIX

No Redis, Celery or API server: the real LangGraph graph runs in this process,
with the analysis and memory handlers loaded through the same env-configured
slots production uses, and the gateway dispatched in-process.

Exit status is 0 only if the planted true relationships PASSed and the injected
false correlation did not.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pramana.analysis.benchmark.demo_dataset import (  # noqa: E402
    DemoManifest,
    PlantedRelationship,
    build_demo_dataset,
)
from pramana.common.config import load_runtime_config  # noqa: E402
from pramana.contracts import ClaimType, GateOutcome, ProofObject, Verdict  # noqa: E402
from pramana.orchestration.adapters import inprocess_verification_adapter  # noqa: E402
from pramana.orchestration.graph import build_graph, run_graph  # noqa: E402
from pramana.orchestration.integration import configured_adapters  # noqa: E402
from pramana.orchestration.run_lifecycle import new_run  # noqa: E402
from pramana.orchestration.state import PramanaState  # noqa: E402

HANDLERS = {
    "PRAMANA_INGEST_HANDLER": "pramana.analysis.handlers:ingest",
    "PRAMANA_PREPARATION_HANDLER": "pramana.analysis.handlers:prepare",
    "PRAMANA_ANALYSIS_HANDLER": "pramana.analysis.handlers:analyze",
    "PRAMANA_MEMORY_HANDLER": "pramana.memory.store:write_verified",
}


def _fmt(value: float | None, spec: str) -> str:
    return "-" if value is None else format(value, spec)


def _find(state: PramanaState, planted: PlantedRelationship) -> str | None:
    """The insight_id of the correlation candidate about exactly this pair, if any."""
    for candidate in state.candidate_insights:
        if candidate.claim_type is ClaimType.CORRELATION and set(candidate.variables) == set(
            planted.variables
        ):
            return candidate.insight_id
    return None


def _print_table(state: PramanaState) -> None:
    proofs = {proof.insight_id: proof for proof in state.proof_objects}
    print(
        f"{'insight_id':<52} {'scan':>7} {'n':>5}  {'stage0':<11} "
        f"{'verdict':<7} {'outcome':<12} {'p':>8} {'q':>8} {'effect':>7}  metric"
    )
    for candidate in state.candidate_insights:
        proof: ProofObject | None = proofs.get(candidate.insight_id)
        evidence = candidate.analysis_evidence
        stage0 = (
            "-"
            if proof is None
            else "screened" if proof.gate_outcome is GateOutcome.NOT_TESTABLE else "admitted"
        )
        print(
            f"{candidate.insight_id:<52} {evidence.get('raw_value', 0.0):>+7.3f} "
            f"{evidence.get('n_observations', 0):>5}  {stage0:<11} "
            f"{proof.verdict.value if proof else '-':<7} "
            f"{proof.gate_outcome.value if proof else '-':<12} "
            f"{_fmt(proof.p_value if proof else None, '.2e'):>8} "
            f"{_fmt(proof.q_value if proof else None, '.2e'):>8} "
            f"{_fmt(proof.effect_size if proof else None, '+.3f'):>7}  "
            f"{proof.effect_metric.value if proof and proof.effect_metric else '-'}"
        )


def _check(state: PramanaState, manifest: DemoManifest) -> bool:
    proofs = {proof.insight_id: proof for proof in state.proof_objects}
    ok = True
    print("\nPlanted relationships")
    for planted in [*manifest.expected_pass, manifest.injected_false]:
        insight_id = _find(state, planted)
        proof = proofs.get(insight_id) if insight_id else None
        if proof is None:
            actual = "NOT PROPOSED" if insight_id is None else "NO PROOF"
            hit = False
        else:
            actual = f"{proof.verdict.value} ({proof.gate_outcome.value})"
            hit = (proof.verdict is Verdict.PASS) == (planted.expected_verdict == "PASS")
        ok &= hit
        print(
            f"  [{'ok' if hit else 'FAIL'}] {' ~ '.join(planted.variables):<40} "
            f"planted rho {planted.in_sample_rho:+.3f} on n={planted.n_observations:<5} "
            f"expected {planted.expected_verdict:<6} got {actual}"
        )
        if proof is not None:
            print(
                f"         p={_fmt(proof.p_value, '.3g')} q={_fmt(proof.q_value, '.3g')} "
                f"family={proof.n_hypotheses_in_batch} "
                f"evidence_score={_fmt(proof.evidence_score, '.3f')}"
            )
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--artifacts-dir", type=Path, default=REPO_ROOT / "artifacts" / "demo")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args()

    csv_path = args.data_dir / "demo" / "nhanes_demo.csv"
    manifest = build_demo_dataset(csv_path, raw_dir=args.data_dir / "raw" / "nhanes")
    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (args.artifacts_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    print(f"Dataset: {manifest.source}")
    print(f"  {manifest.n_rows} rows x {len(manifest.columns)} columns -> {csv_path}")

    for name, value in HANDLERS.items():
        os.environ.setdefault(name, value)
    os.environ.setdefault(
        "PRAMANA_MEMORY_STORE", str(args.artifacts_dir / "verified_insights.jsonl")
    )

    runtime = load_runtime_config()
    runtime = runtime.model_copy(
        update={"logging": runtime.logging.model_copy(update={"level": args.log_level})}
    )
    graph = build_graph(configured_adapters(verify=inprocess_verification_adapter))
    started = time.perf_counter()
    state = run_graph(new_run(str(csv_path), runtime=runtime), graph)
    elapsed = time.perf_counter() - started

    print(f"\nRun {state.run_id}: status={state.status.value} in {elapsed:.1f}s")
    print(f"  path: {' -> '.join(state.visited_nodes)}")
    for error in state.errors:
        print(f"  ERROR at {error.node}: {error.error_type}: {error.message}")
    unusable = state.schema_profile.get("unusable_columns", [])
    print(f"  unusable columns: {unusable or 'none'}")

    proofs = state.proof_objects
    admitted = [p for p in proofs if p.gate_outcome is not GateOutcome.NOT_TESTABLE]
    passed = [p for p in proofs if p.verdict is Verdict.PASS]
    print(
        f"\n{len(state.candidate_insights)} candidates proposed, {len(admitted)} admitted at "
        f"stage 0, {len(passed)} PASS, {len(proofs) - len(passed)} REJECT\n"
    )
    _print_table(state)

    print(f"\nMemory: {len(state.memory_receipts)} records written")
    if state.memory_receipts:
        print(f"  -> {state.memory_receipts[0]['location']}")
    report = state.report or {}
    print(f"Report: {len(report.get('insights', []))} verified insights exposed")

    ok = _check(state, manifest) and not state.errors
    print(f"\nDemo {'SUCCEEDED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
