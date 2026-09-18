"""Run B. Karthikeya's real orchestration graph end to end on a small NHANES frame.

    .venv/Scripts/python.exe scripts/demo_end_to_end.py                       # Windows
    .venv/Scripts/python.exe scripts/demo_end_to_end.py --enable-gateway-llm  # DeepSeek gate

ingest -> subagents -> analysis -> verification -> (memory: explicit no-op) -> report.
No Celery, no Redis, no server, no UI, no memory writes. Adapters are the real ones in
scripts/demo_adapters.py, assembled as WorkflowAdapters(is_stub=False) and compiled
with build_graph(..., allow_stubs=False).

Dataset: data/demo_nhanes_small.csv, built by scripts/build_demo_nhanes.py from three
real NHANES 2017-2018 modules (P_DEMO, P_BMX, P_GLU). If that file is missing, a
synthetic frame of the same shape is used and the run says so loudly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from demo_adapters import DemoSettings, DemoTrace, build_demo_adapters  # noqa: E402

from pramana.common.config import RuntimeConfig  # noqa: E402
from pramana.contracts import ClaimType, GateOutcome, ProofObject, Verdict  # noqa: E402
from pramana.orchestration.graph import build_graph, run_graph  # noqa: E402
from pramana.orchestration.state import PramanaState  # noqa: E402
from pramana.verification.config import load_config as load_verification_config  # noqa: E402

DEFAULT_CSV = REPO_ROOT / "data" / "demo_nhanes_small.csv"
DATASET_SEED = 42  # scripts/build_demo_nhanes.py: row sample, shuffle, pilot decoy

#: Relationships the demo makes an explicit statement about at the end.
BMI_GLUCOSE = frozenset({"BMXBMI", "LBXGLU"})
SHUFFLED_DECOY = "BMXBMI_SHUFFLED_DECOY"
PILOT_DECOY = "BIRTH_MOON_PHASE_PCT"


def _synthetic_fallback(path: Path) -> pd.DataFrame:
    """Same columns as the NHANES build, ~500 rows, one planted BMI->glucose signal,
    one shuffled decoy, one 40-row pilot decoy. Used ONLY when the real CSV is absent."""
    rng = np.random.default_rng(DATASET_SEED)
    n = 500
    age = rng.integers(12, 81, n).astype(float)
    sex = rng.choice([1.0, 2.0], n)
    bmi = np.clip(rng.normal(29, 7, n), 15, 60).round(1)
    signal = 85 + 0.9 * (bmi - 29) + 0.4 * (age - 44) + rng.normal(0, 25, n)
    glucose = np.clip(signal, 45, 400).round(0)
    frame = pd.DataFrame(
        {"RIDAGEYR": age, "RIAGENDR": sex, "BMXBMI": bmi, "LBXGLU": glucose}
    )
    frame[SHUFFLED_DECOY] = rng.permutation(bmi)
    pilot = np.sort(rng.choice(n, 40, replace=False))
    ranks = frame.loc[pilot, "LBXGLU"].rank().to_numpy()
    mixed = 0.6 * (ranks - ranks.mean()) / ranks.std() + rng.standard_normal(40)
    decoy = pd.Series(np.nan, index=frame.index)
    decoy.loc[pilot] = np.round(np.sort(rng.uniform(0, 100, 40)), 1)[
        pd.Series(mixed).rank(method="first").to_numpy(dtype=int) - 1
    ]
    frame[PILOT_DECOY] = decoy
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def _runtime(log_level: str) -> RuntimeConfig:
    """Minimal valid config for one local, non-queued run.

    graph_timeout_seconds is set well above the 30s the integration test uses, on
    purpose: 10k-permutation tests on ~6 claims take ~60s on this machine and the
    demo must not hit the DEGRADED/TimeoutError path. The queue block is required by
    the model but nothing here enqueues anything.
    """
    return RuntimeConfig.model_validate(
        {
            "run": {
                "graph_timeout_seconds": 1800,
                "max_node_retries": 2,
                "on_exhausted_retries": "degrade",
            },
            "queue": {
                "broker_url": "redis://unused.invalid/0",
                "result_backend": "redis://unused.invalid/1",
                "task_soft_time_limit": 90,
                "task_hard_time_limit": 95,
                "result_timeout_seconds": 100,
            },
            "langfuse": {"enabled": False},
            "logging": {"level": log_level, "format": "json"},
        }
    )


def _fmt(value: float | None, spec: str) -> str:
    return "-" if value is None else format(value, spec)


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return str(value)


def _print_schema(state: PramanaState, trace: DemoTrace) -> None:
    print("\nSchema inference (rules; OpenRouter refiner only for UNKNOWN columns)")
    for name, col in state.schema_profile.get("columns", {}).items():
        usable = "usable" if col["usable_for_hypotheses"] else "SKIPPED"
        print(
            f"  {name:<24} {col['role']:<12} conf={col['confidence']:.2f}  "
            f"{usable:<7} {col['reasons'][-1]}"
        )
    for column, decision in trace.refiner_decisions.items():
        print(f"  refiner[{column}] -> {decision}")


def _print_candidates(state: PramanaState, trace: DemoTrace) -> None:
    sources: dict[str, int] = {}
    for candidate in state.candidate_insights:
        src = trace.candidate_sources.get(candidate.insight_id, "?")
        sources[src] = sources.get(src, 0) + 1
    by_source = ", ".join(f"{k}: {v}" for k, v in sources.items()) or "none"
    print(
        f"\nCandidates: {len(state.candidate_insights)} "
        f"(before cap: {trace.candidates_before_cap}; generator -> {by_source})"
    )
    if trace.proposer_error:
        print(f"  OpenRouter proposer failed, rules-only batch used: {trace.proposer_error}")
    for candidate in state.candidate_insights:
        ev = candidate.analysis_evidence
        print(
            f"  {candidate.insight_id:<44} {ev.get('stat', ''):<14} "
            f"{ev.get('raw_value', 0.0):>+7.3f}  n={ev.get('n_observations', 0):<4} "
            f"[{trace.candidate_sources.get(candidate.insight_id, '?')}]"
        )


def _print_proofs(state: PramanaState) -> None:
    claims = {c.insight_id: c.claim for c in state.candidate_insights}
    print(
        f"\n{'insight_id':<44} {'claim':<58} {'verdict':<7} {'gate_outcome':<13} "
        f"{'p':>9} {'q':>9} {'effect':>7}  metric"
    )
    for proof in state.proof_objects:
        print(
            f"{proof.insight_id:<44} {claims.get(proof.insight_id, '?')[:58]:<58} "
            f"{proof.verdict.value:<7} {proof.gate_outcome.value:<13} "
            f"{_fmt(proof.p_value, '.3e'):>9} {_fmt(proof.q_value, '.3e'):>9} "
            f"{_fmt(proof.effect_size, '+.3f'):>7}  "
            f"{proof.effect_metric.value if proof.effect_metric else '-'}"
        )


def _print_rejects(state: PramanaState) -> None:
    """Demo-only: production's safe_report_adapter exposes PASS claims only. For the
    review we also want to see WHY each REJECT was rejected, read straight from
    state.proof_objects. Nothing in the report itself is changed."""
    claims = {c.insight_id: c.claim for c in state.candidate_insights}
    rejected = [p for p in state.proof_objects if p.verdict is Verdict.REJECT]
    print(f"\nREJECTed claims ({len(rejected)}) -- demo output only, not part of the report")
    for proof in rejected:
        metric = proof.effect_metric.value if proof.effect_metric else "-"
        reason = proof.failure_reason or (
            f"gate_outcome={proof.gate_outcome.value}: q={_fmt(proof.q_value, '.3g')} "
            f"effect={_fmt(proof.effect_size, '+.3f')} ({metric})"
        )
        print(f"  {proof.insight_id}")
        print(f"      claim:   {claims.get(proof.insight_id, '?')}")
        print(f"      outcome: {proof.gate_outcome.value}")
        print(f"      reason:  {reason}")


def _find(state: PramanaState, variables: frozenset[str]) -> ProofObject | None:
    proofs = {p.insight_id: p for p in state.proof_objects}
    for candidate in state.candidate_insights:
        if candidate.claim_type is not ClaimType.CORRELATION:
            continue
        if frozenset(candidate.variables) == variables:
            return proofs.get(candidate.insight_id)
    return None


def _print_verdict_checks(state: PramanaState) -> bool:
    print("\nExplicit checks")
    ok = True

    bmi = _find(state, BMI_GLUCOSE)
    hit = bmi is not None and bmi.verdict is Verdict.PASS
    ok &= hit
    if bmi is not None and bmi.effect_metric is not None:
        detail = (
            f" (q={_fmt(bmi.q_value, '.3g')}, {bmi.effect_metric.value}="
            f"{_fmt(bmi.effect_size, '+.3f')}, evidence_score="
            f"{_fmt(bmi.evidence_score, '.3f')})"
        )
    else:
        detail = " (not proposed / no proof)"
    print(
        f"  [{'ok' if hit else 'FAIL'}] BMI vs fasting glucose PASSED: "
        f"{'yes' if hit else 'no'}{detail}"
    )

    shuffled = _find(state, frozenset({SHUFFLED_DECOY, "LBXGLU"}))
    if shuffled is not None:
        hit = shuffled.verdict is Verdict.REJECT
        print(
            f"  [{'ok' if hit else 'FAIL'}] shuffled decoy vs glucose REJECTed by the gateway: "
            f"{shuffled.verdict.value} ({shuffled.gate_outcome.value})"
        )
    else:
        hit = True
        print(
            "  [ok] shuffled decoy vs glucose: NOT PROPOSED -- the analysis module's "
            "|rho| >= 0.15 pre-filter dropped it before the gateway saw it (in-sample "
            "rho ~ 0.04). Not a gateway REJECT: it never reached the gate."
        )
    ok &= hit
    # The shuffled column can still be proposed against OTHER columns (on the 40 pilot
    # rows a chance |rho| can clear 0.15). Every such pair must come back REJECT.
    proofs = {p.insight_id: p for p in state.proof_objects}
    other = [
        proofs[c.insight_id]
        for c in state.candidate_insights
        if SHUFFLED_DECOY in c.variables and "LBXGLU" not in c.variables
    ]
    for proof in other:
        hit = proof.verdict is Verdict.REJECT
        ok &= hit
        print(
            f"  [{'ok' if hit else 'FAIL'}] shuffled decoy in {proof.insight_id}: "
            f"{proof.verdict.value} ({proof.gate_outcome.value}, q={_fmt(proof.q_value, '.3g')})"
        )

    pilot = _find(state, frozenset({PILOT_DECOY, "LBXGLU"}))
    hit = pilot is not None and pilot.verdict is Verdict.REJECT
    ok &= hit
    print(
        f"  [{'ok' if hit else 'FAIL'}] pilot decoy ({PILOT_DECOY}, n=40, planted rho ~0.30) "
        f"REJECTed by the gateway: "
        + (f"{pilot.verdict.value} ({pilot.gate_outcome.value}, p={_fmt(pilot.p_value, '.3g')}, "
           f"q={_fmt(pilot.q_value, '.3g')})" if pilot else "not proposed / no proof")
    )
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument(
        "--enable-gateway-llm",
        action="store_true",
        help="set verification llm.generator='llm' for this run (DeepSeek; needs DEEPSEEK_API_KEY)",
    )
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "artifacts" / "demo_review")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args()

    verification_seed = load_verification_config().statistics.seed
    print("PRAMANA end-to-end demo (real graph, in-process gateway, memory skipped)")
    print(f"  dataset seed:      {DATASET_SEED}   (scripts/build_demo_nhanes.py)")
    print(f"  verification seed: {verification_seed}   (configs/verification.yaml)")

    csv_path = args.csv.resolve()
    synthetic = not csv_path.is_file()
    if synthetic:
        _synthetic_fallback(csv_path)
        print("\n  !!! SYNTHETIC DATA !!! data/demo_nhanes_small.csv was not found, so a synthetic")
        print("  frame of the same shape was generated. This is NOT NHANES. Run")
        print("  scripts/build_demo_nhanes.py to build the real one.\n")
    frame = pd.read_csv(csv_path)
    print(f"  dataset:           {csv_path} ({len(frame)} rows x {len(frame.columns)} cols)"
          f"{'  [SYNTHETIC]' if synthetic else '  [NHANES 2017-2018: P_DEMO + P_BMX + P_GLU]'}")

    settings = DemoSettings.from_env(csv_path, enable_gateway_llm=args.enable_gateway_llm)
    print(
        "  OPENROUTER (analysis assist): "
        + ("ON, model=" + str(settings.openrouter_model) if settings.openrouter_enabled
           else "off (OPENROUTER_API_KEY and/or OPENROUTER_MODEL unset -> rules only, no network)")
    )
    if args.enable_gateway_llm:
        key_state = "set" if os.getenv("DEEPSEEK_API_KEY") else "MISSING -> will fail closed"
        print(f"  gateway generator:  llm (DeepSeek; DEEPSEEK_API_KEY {key_state})")
    else:
        print("  gateway generator:  template (deterministic, offline)")

    adapters, trace = build_demo_adapters(settings)
    graph = build_graph(adapters, allow_stubs=False)
    state = PramanaState(
        run_id=uuid4(),
        runtime=_runtime(args.log_level.upper()),
        dataset_ref=str(csv_path),
        dataset=frame,
    )

    started = time.perf_counter()
    final_state = run_graph(state, graph)
    elapsed = time.perf_counter() - started

    print(f"\nRun {final_state.run_id}: status={final_state.status.value} in {elapsed:.1f}s")
    print(f"  visited_nodes: {final_state.visited_nodes}")
    for error in final_state.errors:
        print(f"  ERROR at {error.node}: {error.error_type}: {error.message}")
    print(f"  cleaned dataset_ref: {final_state.dataset_ref}")
    removed = final_state.cleaning_report.get("columns_removed", [])
    print(f"  cleaning: {final_state.cleaning_report.get('original_shape')} -> "
          f"{final_state.cleaning_report.get('final_shape')}, removed={removed or 'none'}")

    _print_schema(final_state, trace)
    _print_candidates(final_state, trace)
    print(f"\nGateway generator used: {trace.gateway_generator}"
          + (f" ({trace.gateway_model})" if trace.gateway_model else ""))
    _print_proofs(final_state)
    _print_rejects(final_state)

    passed = [p for p in final_state.proof_objects if p.verdict is Verdict.PASS]
    screened = [p for p in final_state.proof_objects if p.gate_outcome is GateOutcome.NOT_TESTABLE]
    print(f"\nTotals: {len(final_state.proof_objects)} proofs, {len(passed)} PASS, "
          f"{len(final_state.proof_objects) - len(passed)} REJECT ({len(screened)} screened out)")
    print(f"Memory: {len(final_state.memory_receipts)} receipts (explicit no-op adapter)")
    report = final_state.report or {}
    exposed = len(report.get("insights", []))
    print(f"Report: {exposed} PASS insights exposed, status={report.get('status')}")

    checks_ok = _print_verdict_checks(final_state)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.out_dir / "report.json"
    proofs_path = args.out_dir / "proof_objects.json"
    report_path.write_text(json.dumps(report, indent=2, default=_json_default), encoding="utf-8")
    proofs_path.write_text(
        json.dumps([p.model_dump(mode="json") for p in final_state.proof_objects], indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote {report_path}\nWrote {proofs_path}")

    ok = checks_ok and not final_state.errors and final_state.status.value == "completed"
    print(f"\nDemo {'SUCCEEDED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
