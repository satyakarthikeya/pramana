"""Report card for forecast claims: false PASS under a null, power, attack false-kill, detection.

What runs. For every replicate the SAME library code the gateway runs, in-process, on a
planted monthly series: the planner's exploration-only choice of method and baseline
(`analysis.planner.forecast_claim._select`), the gateway's own plan and refusals
(`schemes.assign_plan`, which decides NOT_TESTABLE), the backtest and the block sign-flip
test (`verification.stats.forecast`), the effect band and direction (`evidence.evaluate_gate`),
and, for a claim that passes, the six attacks F1-F6. A family of ONE claim, so q = p (the BH
step is a no-op there), like the existing gate report card. `--crosscheck N` runs N replicates
per cell through the REAL gateway (sandboxed subprocess, HMAC stamp) and checks that p-values
and outcomes agree exactly with the in-process path.

Reduced permutations. The card uses `--permutations 999` (production: 10,000) to make
thousands of series affordable. That coarsens p-values (smallest 2/1000) and nothing else.

Planted shapes (monthly, noise sd 2, seasonal amplitude about 10):
  null_rw          random walk, no seasonality. Nothing can beat a last-value forecast here.
  null_rw_literal  the same random walk, baseline forced to seasonal-naive (the design as first
                   written), to show what a seasonal-naive baseline does on a series without
                   a season.
  null_srw         seasonal random walk (y[t] = y[t-12] + noise): seasonal-naive is the best
                   possible forecast, so no method can systematically beat it.
  true             stable seasonal pattern with linear growth: a trend-and-season method beats
                   seasonal-naive for real.
  break            the same, with a level shift of +15 halfway through the series (at the edge
                   between the history and the held-back window).
  break_late       the same shift three quarters of the way through (inside the held-back
                   window), which is the case F5 looks for.
  h1only           the same series as `true`, but the "method" is a planted forecaster that is
                   accurate one period ahead and biased by +7 two periods ahead (about as far
                   off as a seasonal-naive forecast).

    python scripts/calibration/forecast_claim_card.py --reps 200 --workers 4 \\
        --out artifacts/forecast_card.json

Everything here is synthetic and author-built. It shows how the gate behaves on these shapes.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pramana.analysis.planner.forecast_claim import _select  # noqa: E402
from pramana.contracts import (  # noqa: E402
    CandidateInsight,
    ClaimType,
    DataStructure,
    Direction,
    EffectMetric,
    ForecastSpec,
    GateOutcome,
    TableShape,
    render_forecast_claim,
)
from pramana.contracts.attack import AttackOutcome  # noqa: E402
from pramana.verification.attacks.forecast import run_forecast_attacks  # noqa: E402
from pramana.verification.config import ClaimsConfig, VerificationConfig, load_config  # noqa: E402
from pramana.verification.evidence import evaluate_gate  # noqa: E402
from pramana.verification.schemes import (  # noqa: E402
    assign_plan,
    split_rows,
    with_period_column,
)
from pramana.verification.stats.forecast import (  # noqa: E402
    forecast_loss_test,
    period_series,
    run_backtest,
)

SHAPES = ["null_rw", "null_rw_literal", "null_srw", "true", "break", "break_late", "h1only"]
LENGTHS = [36, 60, 120]
HORIZON = 2
STRUCTURE = DataStructure(
    shape=TableShape.TIME_SERIES, time_column="month", period="month", declared_by="caller"
)
ATTACK_IDS = ["F1", "F2", "F3", "F4", "F5", "F6"]


def card_config(n_permutations: int) -> VerificationConfig:
    """The shipped config with the flag on, the template generator, a family of one."""
    shipped = load_config()
    return shipped.model_copy(
        update={
            "claims": ClaimsConfig(forecast_enabled=True),
            "llm": shipped.llm.model_copy(update={"generator": "template"}),
            "statistics": shipped.statistics.model_copy(
                update={"n_permutations": n_permutations, "m_max": 1}
            ),
        }
    )


# --- planted series -----------------------------------------------------------------


def generate(shape: str, n: int, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n)
    seasonal = 10 * np.sin(2 * np.pi * t / 12) + 4 * np.cos(2 * np.pi * t / 6)
    if shape in ("null_rw", "null_rw_literal"):
        return 100 + np.cumsum(rng.normal(0, 2, n))
    if shape == "null_srw":
        y = np.zeros(n)
        y[:12] = rng.normal(0, 5, 12)
        for i in range(12, n):
            y[i] = y[i - 12] + rng.normal(0, 2)
        return 100 + y
    growth = 100 + 0.5 * t + seasonal + rng.normal(0, 2, n)
    if shape == "break":
        return growth + np.where(t >= n // 2, 15.0, 0.0)
    if shape == "break_late":
        return growth + np.where(t >= (3 * n) // 4, 15.0, 0.0)
    return growth  # true, h1only


def planted_horizon_one_only(season: int):
    """Accurate one period ahead; the same forecast plus a bias of 7 two periods ahead."""
    from pramana.verification.stats.forecast import trend_seasonal

    fit = trend_seasonal(season)

    def forecast(train: np.ndarray, horizon: int) -> np.ndarray:
        out = fit(train, horizon).copy()
        out[1:] += 7.0
        return out

    return forecast


# --- one replicate ------------------------------------------------------------------

_WORKER: dict[str, Any] = {}


def _init(n_permutations: int, force_default: bool = False) -> None:
    _WORKER["config"] = card_config(n_permutations)
    _WORKER["force_default"] = force_default


def frames(y: np.ndarray, config: VerificationConfig):
    df = pd.DataFrame(
        {
            "month": pd.period_range("2010-01", periods=len(y), freq="M").to_timestamp(),
            "revenue": y,
        }
    )
    explore, confirm, record = split_rows(df, STRUCTURE, config)
    history = with_period_column(df.iloc[explore].reset_index(drop=True), STRUCTURE)
    rows = with_period_column(df.iloc[confirm].reset_index(drop=True), STRUCTURE)
    return df, explore, history, rows, record


def candidate_for(spec: ForecastSpec) -> CandidateInsight:
    return CandidateInsight(
        insight_id="card",
        claim=render_forecast_claim("revenue", spec),
        claim_type=ClaimType.FORECAST,
        variables=["month", "revenue"],
        dataset_ref="card",
        asserted_direction=Direction.POSITIVE,
        forecast=spec,
    )


def replicate(task: tuple[str, int, int, int, int]) -> dict[str, Any]:
    """One planted series through planner choice, plan, test, band and attacks."""
    shape, n, rep, seed, horizon = task
    config: VerificationConfig = _WORKER["config"]
    rng = np.random.default_rng([seed, SHAPES.index(shape), n, rep])
    y = generate(shape, n, rng)
    _, explore, history, rows, record = frames(y, config)
    settings = config.forecast
    if shape == "null_rw_literal":
        settings = settings.model_copy(update={"baseline": "seasonal_naive"})
    out: dict[str, Any] = {"shape": shape, "n": n, "rep": rep, "horizon": horizon}
    planted = shape == "h1only"
    if planted:
        method, baseline, reduction, how = "trend_seasonal", "seasonal_naive", None, "planted"
    else:
        method, baseline, reduction, how = _select(y[explore], 12, horizon, settings)
    out.update(method=method, baseline=baseline, exploration_reduction=reduction, how=how)
    if reduction is None and not planted and not _WORKER.get("force_default"):
        # the planner refuses a request it cannot choose a baseline for
        out["status"] = "planner_dropped"
        return out
    if reduction is not None and reduction <= 0.0:
        out["status"] = "planner_dropped"
        return out
    spec = ForecastSpec(horizon=horizon, method=method, baseline=baseline, aggregate="mean")
    plan = assign_plan(candidate_for(spec), rows, STRUCTURE, config, history=history, split=record)
    if isinstance(plan, str):
        out.update(status="not_testable", reason=plan)
        return out
    fc = plan.forecast
    both = pd.concat([history, rows], ignore_index=True)
    series = period_series(
        both["__pramana_period__"],
        both["revenue"],
        aggregate="mean",
        test_start_period=fc.test_start_period,
        max_gap_fraction=fc.max_gap_fraction,
    )
    backtest = run_backtest(
        series.values,
        method=method,
        season=fc.season,
        horizon=horizon,
        test_start=series.test_start,
        min_train=fc.min_train,
        baseline=baseline,
        forecaster=planted_horizon_one_only(fc.season) if planted else None,
    )
    result = forecast_loss_test(
        backtest.model_loss,
        backtest.baseline_loss,
        block_length=horizon,
        n_permutations=config.statistics.n_permutations,
        seed=config.statistics.seed,
    )
    decision = evaluate_gate(
        q_value=result.p_value,
        effect_size=result.statistic,
        effect_metric=EffectMetric.MASE_REDUCTION,
        alpha=config.statistics.alpha,
        p_value_floor=config.p_value_floor,
        config=config.evidence,
        asserted_direction=Direction.POSITIVE,
    )
    out.update(
        status="tested",
        p=result.p_value,
        effect=result.statistic,
        n_origins=int(backtest.n_origins),
        gate=decision.outcome.value,
    )
    final = decision.outcome
    attacks: dict[str, str] = {}
    if decision.outcome is GateOutcome.SUPPORTED:
        results = run_forecast_attacks(backtest, config.attacks, config.forecast)
        attacks = {r.attack_id: r.outcome.value for r in results}
        out["f4_calibrated"] = next(
            (r.details.get("calibrated") for r in results if r.attack_id == "F4"), None
        )
        out["attack_applicable"] = {r.attack_id: r.applicable for r in results}
        if any(r.outcome is AttackOutcome.BROKEN for r in results):
            final = GateOutcome.FRAGILE
    out["attacks"] = attacks
    out["final"] = final.value
    return out


# --- summaries ---------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def pct(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.1f}% [{100 * lo:.0f}, {100 * hi:.0f}]"


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(records)
    status = Counter(r["status"] for r in records)
    tested = [r for r in records if r["status"] == "tested"]
    gate_pass = [r for r in tested if r["gate"] == "supported"]
    final_pass = [r for r in tested if r["final"] == "supported"]
    fragile = [r for r in tested if r["final"] == "fragile"]
    effects = np.array([r["effect"] for r in tested]) if tested else np.array([])
    quantiles = [float(q) for q in np.quantile(effects, [0.1, 0.5, 0.9])] if tested else [None] * 3
    broke = {a: sum(1 for r in gate_pass if r["attacks"].get(a) == "broken") for a in ATTACK_IDS}
    not_run = {a: sum(1 for r in gate_pass if r["attacks"].get(a) == "not_run") for a in ATTACK_IDS}
    uncal = sum(1 for r in gate_pass if r.get("f4_calibrated") is False)
    return {
        "reps": n,
        "planner_dropped": status["planner_dropped"],
        "not_testable": status["not_testable"],
        "tested": len(tested),
        "gate_pass": len(gate_pass),
        "final_pass": len(final_pass),
        "fragile": len(fragile),
        "gate_outcomes": dict(Counter(r["gate"] for r in tested)),
        "effect_q10_q50_q90": quantiles,
        "effect_ge_floor": int(sum(effects >= 0.10)) if tested else 0,
        "attack_broke": broke,
        "attack_not_run": not_run,
        "range_not_calibrated": uncal,
        "methods": dict(Counter(r["method"] for r in records)),
        "baselines": dict(Counter(r["baseline"] for r in records)),
        "reasons": dict(Counter(r.get("reason", "")[:60] for r in records if r.get("reason"))),
    }


def render(cells: dict[str, dict[str, Any]], permutations: int, alpha: float) -> str:
    lines = [
        f"Permutations per test: {permutations} (reduced; production 10,000). alpha {alpha}. "
        "Entries: share of ALL replicates unless a denominator is named; 95% Wilson interval.",
        "",
        "| shape | n | reps | planner dropped | not testable | tested | gate pass | final PASS "
        "| FRAGILE | effect q10 / q50 / q90 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for key, s in cells.items():
        shape, n, horizon = key.split("|")
        q = s["effect_q10_q50_q90"]
        shown = "n/a" if q[0] is None else " / ".join(f"{v:+.2f}" for v in q)
        lines.append(
            f"| {shape} | {n} (H={horizon}) | {s['reps']} | {pct(s['planner_dropped'], s['reps'])} "
            f"| {pct(s['not_testable'], s['reps'])} | {s['tested']} "
            f"| {pct(s['gate_pass'], s['reps'])} | {pct(s['final_pass'], s['reps'])} "
            f"| {pct(s['fragile'], s['reps'])} | {shown} |"
        )
    lines += [
        "",
        "Attacks, among claims that cleared the gate (broke / ran / not run):",
        "",
        "| shape | n | gate pass | " + " | ".join(ATTACK_IDS) + " | range not calibrated |",
        "|---|---|---|" + "---|" * (len(ATTACK_IDS) + 1),
    ]
    for key, s in cells.items():
        shape, n, horizon = key.split("|")
        gp = s["gate_pass"]
        cols = " | ".join(
            f"{s['attack_broke'][a]} / {gp - s['attack_not_run'][a]} / {s['attack_not_run'][a]}"
            for a in ATTACK_IDS
        )
        lines.append(
            f"| {shape} | {n} (H={horizon}) | {gp} | {cols} | {s['range_not_calibrated']} |"
        )
    return "\n".join(lines)


# --- cross-check against the real gateway ------------------------------------------


def crosscheck(count: int, permutations: int, seed: int) -> list[dict[str, Any]]:
    """Real gateway vs the in-process path on the same series: p and outcome must agree."""
    from pramana.verification.gateway import verify_batch_with_summary

    config = card_config(permutations)
    _WORKER["config"] = config
    results = []
    for shape, n in (("true", 60), ("null_srw", 60), ("break", 120)):
        for rep in range(count):
            mine = replicate((shape, n, rep, seed, HORIZON))
            if mine["status"] != "tested":
                results.append({"shape": shape, "n": n, "rep": rep, "skipped": mine["status"]})
                continue
            rng = np.random.default_rng([seed, SHAPES.index(shape), n, rep])
            y = generate(shape, n, rng)
            df, explore, history, rows, record = frames(y, config)
            spec = ForecastSpec(
                horizon=HORIZON, method=mine["method"], baseline=mine["baseline"], aggregate="mean"
            )
            proofs, _ = verify_batch_with_summary(
                [candidate_for(spec)],
                df.iloc[record_rows(df, explore, rows)].reset_index(drop=True),
                config,
                structure=STRUCTURE,
                split=record,
                history=df.iloc[explore].reset_index(drop=True),
            )
            proof = proofs[0]
            results.append(
                {
                    "shape": shape,
                    "n": n,
                    "rep": rep,
                    "p_same": proof.p_value == mine["p"],
                    "effect_same": abs((proof.effect_size or 0.0) - mine["effect"]) < 1e-12,
                    "outcome_same": proof.gate_outcome.value == mine["final"],
                    "real": proof.gate_outcome.value,
                    "in_process": mine["final"],
                }
            )
    return results


def record_rows(df: pd.DataFrame, explore: np.ndarray, rows: pd.DataFrame) -> np.ndarray:
    return np.setdiff1d(np.arange(len(df)), explore)


# --- main ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--reps", type=int, default=200)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--permutations", type=int, default=999)
    parser.add_argument("--seed", type=int, default=20261025)
    parser.add_argument("--shapes", nargs="*", default=SHAPES)
    parser.add_argument("--lengths", nargs="*", type=int, default=LENGTHS)
    parser.add_argument("--horizon", type=int, default=HORIZON)
    parser.add_argument(
        "--force-default",
        action="store_true",
        help="diagnostic: test claims the planner would refuse for lack of exploration periods, "
        "with the default method and the seasonal-naive baseline",
    )
    parser.add_argument("--crosscheck", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if args.crosscheck:
        found = crosscheck(args.crosscheck, args.permutations, args.seed)
        compared = [r for r in found if "skipped" not in r]
        ok = sum(r["p_same"] and r["effect_same"] and r["outcome_same"] for r in compared)
        print(json.dumps({"compared": len(compared), "identical": ok, "detail": found}, indent=1))
        return

    config = card_config(args.permutations)
    store: dict[str, Any] = {}
    if args.out and args.out.exists():
        store = json.loads(args.out.read_text())
    cells: dict[str, dict[str, Any]] = store.get("cells", {})
    raw: dict[str, list[dict[str, Any]]] = store.get("raw", {})
    with Pool(
        args.workers, initializer=_init, initargs=(args.permutations, args.force_default)
    ) as pool:
        for shape in args.shapes:
            for n in args.lengths:
                key = f"{shape}|{n}|{args.horizon}"
                if key in cells and cells[key]["reps"] >= args.reps:
                    continue
                started = time.time()
                tasks = [(shape, n, rep, args.seed, args.horizon) for rep in range(args.reps)]
                records = list(pool.imap(replicate, tasks, chunksize=2))
                cells[key] = summarize(records)
                raw[key] = records
                print(f"{key}: {time.time() - started:.0f}s {cells[key]}", flush=True)
                if args.out:
                    args.out.parent.mkdir(parents=True, exist_ok=True)
                    args.out.write_text(
                        json.dumps(
                            {
                                "seed": args.seed,
                                "permutations": args.permutations,
                                "reps": args.reps,
                                "cells": cells,
                                "raw": raw,
                            }
                        )
                    )
    print(render(cells, args.permutations, config.statistics.alpha))


if __name__ == "__main__":
    main()
