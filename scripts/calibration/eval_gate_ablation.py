"""E1: gate versus no gate on planted-truth tables (thesis headline experiment).

Design, metrics, seeds and the "bad result" lines are written in
docs/evidence/GATE_VS_NO_GATE_2026-10-25.md BEFORE the first run.

K seeded tables, 12 candidate claims each, enumerated by code (no planner, no model).
A known number of claims are truly related (rho in {0.15, 0.3, 0.5}), the rest are null.
Three structures: independent rows, shared season (many rows a month), entity clusters.

Arms, scored against the planted truth:

* A  naive:      uncorrected two-sided p < 0.05 on ALL rows, right sign (row-level
                 Spearman or Mann-Whitney; ignores season and clusters, as a naive tool does).
* B  BH only:    the real gateway's raw p on the CONFIRMATION half, BH q < alpha over the
                 12 claims, right sign. No effect floor, no attacks.
* B+ BH + floor: B plus the effect-size floor (gate outcome SUPPORTED or FRAGILE).
                 An extra rung of the ladder, free from the same gateway run.
* C  full gate:  the real gateway verdict == PASS (split, BH, effect band, attacks).

B, B+ and C come from ONE gateway call per table; they differ only in which stage's
output is read. Arm A does not use the gateway.

    PYTHONPATH=src python scripts/calibration/eval_gate_ablation.py \
        --tables 200 --permutations 1000 --workers 8 --out artifacts/e1_gate_ablation.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pramana.contracts import (  # noqa: E402
    CandidateInsight,
    ClaimType,
    DataStructure,
    Direction,
    GateOutcome,
    TableShape,
    Verdict,
)
from pramana.verification.config import VerificationConfig, load_config  # noqa: E402
from pramana.verification.executor import runner as _runner  # noqa: E402
from pramana.verification.gateway import verify_batch  # noqa: E402
from pramana.verification.schemes import confirmation_frame  # noqa: E402

N_CLAIMS = 12
RHOS = (0.15, 0.3, 0.5)
N_TRUE = (2, 4, 6)
STRUCTURES = ("independent", "season", "entity")
ARMS = ("A_naive", "B_bh_only", "Bplus_bh_floor", "C_full_gate")
BASE_SEED = 20261025

INDEPENDENT = DataStructure.independent_rows()
TRANSACTIONS = DataStructure(shape=TableShape.TRANSACTIONS, time_column="month",
                             period="month", entity_column=None, declared_by="caller")
PANEL = DataStructure(shape=TableShape.PANEL, time_column="month", entity_column="entity",
                      period="month", declared_by="caller")
STRUCTURE_OF = {"independent": INDEPENDENT, "season": TRANSACTIONS, "entity": PANEL}


_SUBPROCESS_RUN_ONCE = _runner._run_once


def _plain(value):
    """numpy scalars are not JSON types; everything else is text (as in the harness)."""
    item = getattr(value, "item", None)
    return item() if callable(item) else str(value)


def _run_once_in_process(program, frame, config):
    """Same checks as the sandbox runner, minus the subprocess.

    The vetted template source is exec'd in THIS process with a fresh provenance nonce,
    the payload goes through a JSON round trip exactly as the subprocess output would,
    and the real `_validate_payload` (structure, finite effect, provenance stamp, scheme,
    resample count, seed) judges it. `execute()` still applies the import and column
    policies before calling this. What is skipped is process isolation, memory and time
    limits; the sandbox costs about 30-40 s of interpreter start-up per claim on this
    machine, which would make 2,400 claims take days. Safe here only because the code
    is the repository's own template, never model-written. Use --sandbox to avoid this.
    """
    import json as _json
    import types

    from pramana.verification.stats import provenance

    nonce = provenance.new_nonce()
    previous = provenance._NONCE
    provenance._NONCE = nonce
    try:
        module = types.ModuleType("falsification_program")
        exec(compile(program.source, "falsification_program.py", "exec"), module.__dict__)  # noqa: S102
        payload = module.falsify(frame.copy())
        payload = _json.loads(_json.dumps(payload, default=_plain))
    except Exception as error:  # same shape as a crashed subprocess: retryable failure
        return None, f"execution raised {type(error).__name__}: {error}", True
    finally:
        provenance._NONCE = previous
    reason = _runner._validate_payload(payload, nonce, config, program.scheme.value)
    return (None, reason, False) if reason else (payload, None, False)


def use_executor(sandbox: bool) -> None:
    """Select the real subprocess sandbox or the in-process shim for this process."""
    _runner._run_once = _SUBPROCESS_RUN_ONCE if sandbox else _run_once_in_process


def experiment_config(n_permutations: int) -> VerificationConfig:
    """Shipped config with the vetted template generator and a reduced permutation count.

    Only `llm.generator` and `statistics.n_permutations` differ from configs/verification.yaml
    (m_max stays at its shipped 40 so the loader's resolution rule still holds at 1000).
    Alpha, bands, attacks and the split are the shipped values.
    """
    shipped = load_config()
    return shipped.model_copy(update={
        "llm": shipped.llm.model_copy(update={"generator": "template"}),
        "statistics": shipped.statistics.model_copy(update={"n_permutations": n_permutations}),
    })


# --- planted tables ------------------------------------------------------------


def table_spec(k: int) -> dict[str, Any]:
    """Balanced 27-cell cycle over structure x rho x number of true claims (deterministic)."""
    return {"k": k, "structure": STRUCTURES[k % 3], "rho": RHOS[(k // 3) % 3],
            "n_true": N_TRUE[(k // 9) % 3]}


def make_table(spec: dict[str, Any]) -> tuple[pd.DataFrame, list[CandidateInsight], set[str]]:
    """The table, its 12 claims (code-enumerated) and the ids of the truly related ones."""
    rng = np.random.default_rng([BASE_SEED, spec["k"]])
    rho = spec["rho"]
    true_idx = set(rng.permutation(N_CLAIMS)[: spec["n_true"]].tolist())
    r = [rho if j in true_idx else 0.0 for j in range(N_CLAIMS)]
    cols: dict[str, Any] = {}
    kind = spec["structure"]
    if kind == "independent":
        n = 200
        for j in range(N_CLAIMS):
            x = rng.normal(size=n)
            cols[f"x{j}"] = x
            cols[f"y{j}"] = r[j] * x + math.sqrt(1 - r[j] ** 2) * rng.normal(size=n)
    elif kind == "season":
        months = pd.date_range("2021-01-01", periods=36, freq="MS")
        idx = np.repeat(np.arange(36), 6)
        cols["month"] = np.repeat(months.to_numpy(), 6)
        for j in range(N_CLAIMS):
            season = 3.0 * np.sin(2 * np.pi * (idx + rng.integers(0, 12)) / 12)
            x = rng.normal(size=idx.size)
            cols[f"x{j}"] = season + x
            cols[f"y{j}"] = season + r[j] * x + math.sqrt(1 - r[j] ** 2) * rng.normal(size=idx.size)
    else:
        n_ent, n_per = 40, 6
        months = pd.date_range("2021-01-01", periods=n_per, freq="MS")
        ent = np.repeat(np.arange(n_ent), n_per)
        cols["month"] = np.tile(months.to_numpy(), n_ent)
        cols["entity"] = np.array([f"e{i}" for i in ent])
        for j in range(N_CLAIMS):
            lab = rng.permutation(np.array([1.0] * (n_ent // 2) + [-1.0] * (n_ent // 2)))
            level = r[j] * lab + math.sqrt(1 - r[j] ** 2) * rng.normal(size=n_ent)
            cols[f"label{j}"] = np.where(lab[ent] > 0, "b", "a")
            cols[f"y{j}"] = level[ent] + 0.5 * rng.normal(size=ent.size)
    frame = pd.DataFrame(cols)
    claims: list[CandidateInsight] = []
    for j in range(N_CLAIMS):
        if kind == "entity":
            vars_, ctype, ref = [f"label{j}", f"y{j}"], ClaimType.GROUP_DIFFERENCE, "b"
        else:
            vars_, ctype, ref = [f"x{j}", f"y{j}"], ClaimType.CORRELATION, None
        claims.append(CandidateInsight(
            insight_id=f"t{spec['k']}c{j}", claim=f"{vars_[-1]} is associated with {vars_[0]}",
            claim_type=ctype, variables=vars_, dataset_ref="e1", analysis_evidence={},
            asserted_direction=Direction.POSITIVE, reference_group=ref))
    return frame, claims, {f"t{spec['k']}c{j}" for j in true_idx}


# --- arms -----------------------------------------------------------------------


def naive_reports(frame: pd.DataFrame, claims: list[CandidateInsight], alpha: float) -> set[str]:
    """Arm A: uncorrected two-sided p < alpha on every row, with the asserted sign."""
    out: set[str] = set()
    for c in claims:
        a, b = c.variables
        if c.claim_type is ClaimType.GROUP_DIFFERENCE:
            hi = frame.loc[frame[a] == "b", b]
            lo = frame.loc[frame[a] != "b", b]
            p = sps.mannwhitneyu(hi, lo, alternative="two-sided").pvalue
            positive = hi.mean() > lo.mean()
        else:
            res = sps.spearmanr(frame[a], frame[b])
            positive, p = res.statistic > 0, res.pvalue
        if p < alpha and positive:
            out.add(c.insight_id)
    return out


def score(reported: set[str], truth: set[str]) -> dict[str, Any]:
    tp = len(reported & truth)
    return {"reported": len(reported), "false": len(reported) - tp, "true_kept": tp,
            "n_true": len(truth)}


def run_table(job: tuple[dict[str, Any], int, bool]) -> dict[str, Any]:
    """One table through all arms. Never raises: a crash is recorded and counted."""
    spec, n_permutations, sandbox = job
    use_executor(sandbox)
    config = experiment_config(n_permutations)
    config = config.model_copy(update={"statistics": config.statistics.model_copy(
        update={"seed": BASE_SEED + spec["k"]})})
    alpha = config.statistics.alpha
    frame, claims, truth = make_table(spec)
    structure = STRUCTURE_OF[spec["structure"]]
    row: dict[str, Any] = {"spec": spec, "arms": {}, "errors": []}

    t0 = time.perf_counter()
    reported_a = naive_reports(frame, claims, alpha)
    row["arms"]["A_naive"] = {**score(reported_a, truth), "seconds": time.perf_counter() - t0}

    t0 = time.perf_counter()
    try:
        # The split is the one the gate itself would make; the gateway tests the later half.
        conf, split = confirmation_frame(frame, structure, config)
        proofs = verify_batch(claims, conf, config, structure=structure, split=split)
    except Exception as error:  # fail closed: report nothing for B/B+/C, record why
        row["errors"].append(f"{type(error).__name__}: {error}")
        proofs = []
    seconds = time.perf_counter() - t0
    b = {p.insight_id for p in proofs if p.q_value is not None and p.q_value < alpha
         and p.observed_direction is Direction.POSITIVE}
    bplus = {p.insight_id for p in proofs if p.gate_outcome in
             (GateOutcome.SUPPORTED, GateOutcome.FRAGILE)}
    c = {p.insight_id for p in proofs if p.verdict is Verdict.PASS}
    row["arms"]["B_bh_only"] = {**score(b, truth), "seconds": seconds}
    row["arms"]["Bplus_bh_floor"] = {**score(bplus, truth), "seconds": seconds}
    row["arms"]["C_full_gate"] = {**score(c, truth), "seconds": seconds}
    row["n_tested"] = sum(p.q_value is not None for p in proofs)
    row["n_not_testable"] = sum(p.gate_outcome is GateOutcome.NOT_TESTABLE for p in proofs)
    row["n_fragile"] = sum(p.gate_outcome is GateOutcome.FRAGILE for p in proofs)
    row["n_hypotheses_in_batch"] = max((p.n_hypotheses_in_batch or 0 for p in proofs), default=0)
    return row


# --- aggregation ----------------------------------------------------------------


def _mean_se(values: list[float]) -> tuple[float, float, float, float]:
    arr = np.asarray(values, dtype=float)
    mean = float(arr.mean()) if arr.size else float("nan")
    se = float(arr.std(ddof=1) / math.sqrt(arr.size)) if arr.size > 1 else float("nan")
    return mean, se, mean - 1.96 * se, mean + 1.96 * se


def _wilson(k: int, n: int) -> tuple[float, float]:
    ci = sps.binomtest(k, n).proportion_ci(confidence_level=0.95, method="wilson")
    return float(ci.low), float(ci.high)


def summarise(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    """Per-arm summary. Means are over tables; SE is the Monte-Carlo SE across tables."""
    per = [r["arms"][arm] for r in rows]
    fdp = [(p["false"] / p["reported"]) if p["reported"] else 0.0 for p in per]
    recall = [(p["true_kept"] / p["n_true"]) for p in per]
    out: dict[str, Any] = {"tables": len(per)}
    for name, vals in (("reported_per_table", [p["reported"] for p in per]),
                       ("false_per_table", [p["false"] for p in per]),
                       ("recall", recall), ("fdp", fdp),
                       ("seconds_per_table", [p["seconds"] for p in per])):
        m, se, lo, hi = _mean_se(vals)
        out[name] = {"mean": m, "se": se, "ci_low": lo, "ci_high": hi}
    any_false = sum(p["false"] > 0 for p in per)
    lo, hi = _wilson(any_false, len(per))
    out["tables_with_any_false_report"] = {"count": any_false, "share": any_false / len(per),
                                           "ci_low": lo, "ci_high": hi}
    reported = sum(p["reported"] for p in per)
    out["pooled_false_discovery_share"] = (sum(p["false"] for p in per) / reported
                                           if reported else 0.0)
    out["pooled_reported"] = reported
    out["pooled_true_kept"] = sum(p["true_kept"] for p in per)
    out["pooled_true_total"] = sum(p["n_true"] for p in per)
    return out


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"overall": {a: summarise(rows, a) for a in ARMS}, "by_rho": {},
                              "by_structure": {}}
    for rho in RHOS:
        sub = [r for r in rows if r["spec"]["rho"] == rho]
        if sub:
            result["by_rho"][str(rho)] = {a: summarise(sub, a) for a in ARMS}
    for s in STRUCTURES:
        sub = [r for r in rows if r["spec"]["structure"] == s]
        if sub:
            result["by_structure"][s] = {a: summarise(sub, a) for a in ARMS}
    result["gateway_errors"] = [{"k": r["spec"]["k"], "errors": r["errors"]}
                                for r in rows if r["errors"]]
    result["mean_not_testable_per_table"] = float(np.mean([r["n_not_testable"] for r in rows]))
    result["mean_tested_per_table"] = float(np.mean([r["n_tested"] for r in rows]))
    return result


def render(agg: dict[str, Any]) -> str:
    lines = [f"{'arm':<16}{'reported':>9}{'false':>8}{'recall':>8}{'FDP':>8}"
             f"{'any-false':>11}{'sec':>7}"]
    for arm, s in agg["overall"].items():
        lines.append(
            f"{arm:<16}{s['reported_per_table']['mean']:9.2f}{s['false_per_table']['mean']:8.2f}"
            f"{s['recall']['mean']:8.3f}{s['fdp']['mean']:8.3f}"
            f"{s['tables_with_any_false_report']['share']:11.3f}"
            f"{s['seconds_per_table']['mean']:7.2f}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables", type=int, default=200)
    parser.add_argument("--permutations", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--sandbox", action="store_true",
                        help="run every test in the real subprocess sandbox (slow)")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    jobs = [(table_spec(k), args.permutations, args.sandbox) for k in range(args.tables)]
    t0 = time.perf_counter()
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(run_table, jobs))
    else:
        rows = [run_table(j) for j in jobs]
    agg = aggregate(rows)
    meta = {"tables": args.tables, "claims_per_table": N_CLAIMS,
            "permutations": args.permutations, "base_seed": BASE_SEED,
            "workers": args.workers, "sandbox": args.sandbox,
            "wall_seconds": time.perf_counter() - t0,
            "alpha": experiment_config(args.permutations).statistics.alpha}
    print(render(agg))
    print(f"wall {meta['wall_seconds']:.0f}s, gateway errors: {len(agg['gateway_errors'])}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"meta": meta, "summary": agg, "rows": rows}, indent=2)
                            + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
