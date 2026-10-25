"""The gate's report card (design v3, S2): false-positive rate, power and attack false-kills.

Runs the REAL gateway (template tests, sandbox, BH, band) on planted tables:

* nulls, one per permutation scheme: the share of runs where the gate's q-value is below
  alpha although nothing is related (should be near or below alpha);
* planted effects: the share of runs where the gate finds them (power);
* the attack set on a true, moderate effect: the share it wrongly breaks (target <= 0.15).

It is slow (one sandboxed test per replicate), so the full numbers are produced here and
recorded in docs/DESIGN_verification_gateway_v3.md; the unit test only checks the plumbing
at a handful of replicates. A rate over R replicates has a standard error near
sqrt(p(1-p)/R): read it with that in mind.

    python scripts/calibration/gate_report_card.py --reps 100 --out artifacts/gate_report_card.json
    python scripts/calibration/gate_report_card.py --extra --reps 100   # families + attack rates

`--extra` adds two things the base card cannot show because it tests a family of ONE claim:
a correlated family of 8 claims through the real gateway (what BH, Holm and no correction do
to false PASSes and power), and the attack set's false-kill and false-survive rates under the
`point` and `interval` A2 rules. The attack rows use a Spearman test plus the effect floor as a
stand-in for the gate so thousands of tables can be tried; read them as rates for claims that
cleared the gate, not as a second run of it.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pramana.contracts import (  # noqa: E402
    CandidateInsight,
    ClaimType,
    DataStructure,
    Direction,
    GateOutcome,
    PermutationScheme,
    TableShape,
)
from pramana.verification.attacks import ClaimView, run_attacks  # noqa: E402
from pramana.verification.config import VerificationConfig, load_config  # noqa: E402
from pramana.verification.gateway import verify_batch  # noqa: E402
from pramana.verification.schemes import with_period_column  # noqa: E402

Frame = Callable[[np.random.Generator], pd.DataFrame]


def pinned_config(n_permutations: int = 1000) -> VerificationConfig:
    """The shipped config, vetted-template generator, a family of one (so m_max = 1)."""
    shipped = load_config()
    return shipped.model_copy(
        update={
            "llm": shipped.llm.model_copy(update={"generator": "template"}),
            "statistics": shipped.statistics.model_copy(
                update={"n_permutations": n_permutations, "m_max": 1}
            ),
        }
    )


def _claim(claim_type: ClaimType, variables: list[str], direction: Direction | None):
    return CandidateInsight(
        insight_id="card",
        claim=f"{variables[-1]} is associated with {variables[0]}",
        claim_type=claim_type,
        variables=variables,
        dataset_ref="report_card",
        analysis_evidence={},
        asserted_direction=direction,
    )


# --- planted tables -----------------------------------------------------------


def cross_section(effect: float) -> Frame:
    def make(rng: np.random.Generator) -> pd.DataFrame:
        x = rng.normal(size=100)
        return pd.DataFrame({"x": x, "y": effect * x + rng.normal(size=100)})

    return make


def random_walks() -> Frame:
    """Two unrelated random walks: a free shuffle calls them related; the right null must not."""

    def make(rng: np.random.Generator) -> pd.DataFrame:
        months = pd.date_range("2020-01-01", periods=48, freq="MS")
        return pd.DataFrame(
            {
                "month": months,
                "x": np.cumsum(rng.normal(size=48)),
                "y": np.cumsum(rng.normal(size=48)),
            }
        )

    return make


def seasonal_transactions(effect: float) -> Frame:
    """Many rows per month; both columns follow the same season, plus `effect` within months."""

    def make(rng: np.random.Generator) -> pd.DataFrame:
        rows = []
        for month in pd.date_range("2021-01-01", periods=36, freq="MS"):
            season = 3.0 * math.sin(2 * math.pi * month.month / 12)
            for _ in range(6):
                x = rng.normal()
                rows.append(
                    {
                        "month": month,
                        "x": season + x,
                        "y": season + effect * x + rng.normal(),
                    }
                )
        return pd.DataFrame(rows)

    return make


def entity_groups(effect: float) -> Frame:
    """12 entities, a fixed label per entity, `effect` shift for the second label."""

    def make(rng: np.random.Generator) -> pd.DataFrame:
        rows = []
        for entity in range(12):
            label = "a" if entity % 2 == 0 else "b"
            level = rng.normal() + (effect if label == "b" else 0.0)
            for month in pd.date_range("2021-01-01", periods=12, freq="MS"):
                rows.append(
                    {"month": month, "entity": f"e{entity}", "label": label,
                     "y": level + rng.normal(0, 0.5)}
                )
        return pd.DataFrame(rows)

    return make


INDEPENDENT = DataStructure.independent_rows()
SERIES = DataStructure(shape=TableShape.TIME_SERIES, time_column="month", period="month",
                       declared_by="caller")
TRANSACTIONS = DataStructure(shape=TableShape.TRANSACTIONS, time_column="month",
                             period="month", entity_column=None, declared_by="caller")
PANEL = DataStructure(shape=TableShape.PANEL, time_column="month", entity_column="entity",
                      period="month", declared_by="caller")

#: (name, scheme the gate should assign, planted effect, table, structure, claim)
SCENARIOS: list[tuple[str, PermutationScheme, bool, Frame, DataStructure, CandidateInsight]] = [
    ("null: independent rows", PermutationScheme.FREE, False, cross_section(0.0), INDEPENDENT,
     _claim(ClaimType.CORRELATION, ["x", "y"], Direction.POSITIVE)),
    ("null: two random walks", PermutationScheme.BLOCK_DIFFERENCED, False, random_walks(), SERIES,
     _claim(ClaimType.CORRELATION, ["x", "y"], Direction.POSITIVE)),
    ("null: shared season, many rows a month", PermutationScheme.STRATIFIED, False,
     seasonal_transactions(0.0), TRANSACTIONS,
     _claim(ClaimType.CORRELATION, ["x", "y"], Direction.POSITIVE)),
    ("null: label fixed per entity", PermutationScheme.CLUSTER, False, entity_groups(0.0), PANEL,
     _claim(ClaimType.GROUP_DIFFERENCE, ["label", "y"], None)),
    ("power: rho about 0.3, 100 rows", PermutationScheme.FREE, True, cross_section(0.4),
     INDEPENDENT, _claim(ClaimType.CORRELATION, ["x", "y"], Direction.POSITIVE)),
    ("power: within-month link, 216 rows", PermutationScheme.STRATIFIED, True,
     seasonal_transactions(0.5), TRANSACTIONS,
     _claim(ClaimType.CORRELATION, ["x", "y"], Direction.POSITIVE)),
]


def run_scenario(name: str, scheme: PermutationScheme, planted: bool, make: Frame,
                 structure: DataStructure, claim: CandidateInsight, reps: int,
                 config: VerificationConfig, seed: int) -> dict[str, Any]:
    """Share of replicates where the gate's q < alpha (null: false positive; planted: power)."""
    rng = np.random.default_rng(seed)
    significant = passed = wrong_scheme = 0
    alpha = config.statistics.alpha
    for _ in range(reps):
        proof = verify_batch([claim], make(rng), config, structure=structure)[0]
        wrong_scheme += proof.permutation_scheme is not scheme
        significant += proof.q_value is not None and proof.q_value < alpha
        passed += proof.gate_outcome in (GateOutcome.SUPPORTED, GateOutcome.FRAGILE)
    rate = significant / reps
    return {
        "scenario": name,
        "kind": "power" if planted else "false_positive",
        "scheme": scheme.value,
        "reps": reps,
        "rate_q_below_alpha": rate,
        "standard_error": math.sqrt(max(rate * (1 - rate), 1e-12) / reps),
        "rate_passed_gate": passed / reps,
        "assigned_wrong_scheme": wrong_scheme,
    }


def attack_false_kill(reps: int, config: VerificationConfig, seed: int) -> dict[str, Any]:
    """Share of true, moderate effects (rho about 0.4, 200 rows) that any attack breaks."""
    rng = np.random.default_rng(seed)
    claim = ClaimView(claim_type=ClaimType.CORRELATION, var_x="x", var_y="y",
                      scheme=PermutationScheme.FREE)
    killed = 0
    for _ in range(reps):
        x = rng.normal(size=200)
        frame = with_period_column(
            pd.DataFrame({"x": x, "y": 0.45 * x + rng.normal(size=200)}), INDEPENDENT
        )
        results = run_attacks(claim, frame, config.attacks, seed=int(rng.integers(1 << 30)))
        killed += any(r.outcome.value == "broken" for r in results)
    rate = killed / reps
    return {"scenario": "attacks on a true moderate effect", "kind": "false_kill", "reps": reps,
            "rate_any_attack_broken": rate,
            "standard_error": math.sqrt(max(rate * (1 - rate), 1e-12) / reps)}


def report_card(reps: int, seed: int = 20261024, n_permutations: int = 1000) -> dict[str, Any]:
    config = pinned_config(n_permutations)
    rows = [run_scenario(*s, reps, config, seed + i) for i, s in enumerate(SCENARIOS)]
    rows.append(attack_false_kill(reps, config, seed + 99))
    return {"alpha": config.statistics.alpha, "n_permutations": n_permutations,
            "reps": reps, "seed": seed, "rows": rows}


# --- extra: a correlated family of 8, and the attack rates ----------------------


def _family_table(rng: np.random.Generator, n: int, beta: float, k_true: int) -> pd.DataFrame:
    """A hub H; `k_true` of three T columns follow it; five mutually correlated nulls N.

    Claims are pairs, so null claims share columns with true ones and with each other.
    """
    hub = rng.normal(size=n)
    cols = {"H": hub}
    for i in range(3):
        cols[f"T{i}"] = (beta * hub if i < k_true else 0.0) + rng.normal(size=n)
    shared = rng.normal(size=n)
    for j in range(5):
        cols[f"N{j}"] = np.sqrt(0.6) * shared + np.sqrt(0.4) * rng.normal(size=n)
    return pd.DataFrame(cols)


def _family_claims(k_true: int) -> list[tuple[CandidateInsight, bool]]:
    pairs = [("H", f"T{i}") for i in range(k_true)] + [
        ("H", "N0"), ("H", "N1"), ("H", "N2"), ("T0", "N0"), ("T1", "N1"), ("T2", "N2"),
        ("H", "N3"), ("T0", "N3"),
    ][: 8 - k_true]
    claims = []
    for i, (a, b) in enumerate(pairs):
        claim = _claim(ClaimType.CORRELATION, [a, b], None)
        claims.append((claim.model_copy(update={"insight_id": f"f{i}"}), i < k_true))
    return claims


def _holm(p_values: list[float], alpha: float) -> list[bool]:
    order = np.argsort(p_values)
    keep = [False] * len(p_values)
    for rank, index in enumerate(order):
        if p_values[index] > alpha / (len(p_values) - rank):
            break
        keep[index] = True
    return keep


def family_card(
    reps: int, seed: int = 20261025, n_permutations: int = 1000
) -> list[dict[str, Any]]:
    """False PASSes and power in a family of 8 under no correction, BH (the gate) and Holm."""
    base = pinned_config(n_permutations)
    config = base.model_copy(
        update={"statistics": base.statistics.model_copy(update={"m_max": 8}),
                "attacks": base.attacks}
    )
    alpha = config.statistics.alpha
    out = []
    for name, n, beta, k_true in [
        ("family of 8, all null, n=100", 100, 0.3, 0),
        ("family of 8, 3 true (rho about 0.3), n=100", 100, 0.3, 3),
        ("family of 8, 3 true (rho about 0.4), n=100", 100, 0.45, 3),
    ]:
        rng = np.random.default_rng(seed + n + k_true)
        claims = _family_claims(k_true)
        acc = {m: [0.0, 0, 0.0] for m in ("none", "bh", "holm")}  # false share, any false, power
        for _ in range(reps):
            frame = _family_table(rng, n, beta, k_true)
            proofs = verify_batch([c for c, _ in claims], frame, config, structure=INDEPENDENT)
            truth = [t for _, t in claims]
            p = [pr.p_value if pr.p_value is not None else 1.0 for pr in proofs]
            q_pass = [pr.q_value is not None and pr.q_value < alpha for pr in proofs]
            arms = {"none": [v < alpha for v in p], "bh": q_pass, "holm": _holm(p, alpha)}
            for arm, rejected in arms.items():
                false = sum(r_ and not t for r_, t in zip(rejected, truth, strict=True))
                total = sum(rejected)
                acc[arm][0] += false / total if total else 0.0
                acc[arm][1] += false > 0
                acc[arm][2] += (
                    sum(r_ and t for r_, t in zip(rejected, truth, strict=True)) / k_true
                    if k_true else 0.0
                )
        for arm, (fdp, any_false, power) in acc.items():
            out.append({"scenario": name, "kind": "family", "arm": arm, "reps": reps,
                        "false_discovery_rate": fdp / reps, "any_false_pass": any_false / reps,
                        "power": power / reps if k_true else None})
    return out


def _attack_table(rng: np.random.Generator, n: int, kind: str, rho: float) -> pd.DataFrame:
    x = rng.normal(size=n)
    if kind == "confounded":
        z = rng.normal(size=n)
        return pd.DataFrame({"x": 0.8 * z + 0.6 * rng.normal(size=n),
                             "y": 0.8 * z + 0.6 * rng.normal(size=n), "z": z,
                             "site": rng.choice(list("abc"), size=n)})
    return pd.DataFrame({"x": x, "y": rho * x + np.sqrt(1 - rho**2) * rng.normal(size=n),
                         "z": rng.normal(size=n), "site": rng.choice(list("abc"), size=n)})


def attack_card(reps: int, seed: int = 20261026) -> list[dict[str, Any]]:
    """Share of gate-clearing tables the attack set breaks, under each A2 rule.

    `true` rows are false kills (lower is better); `no effect` rows are the luck-passes the
    attacks remove (higher removes more, but they are not a defence against false
    positives); `confounded` is a flaw the attacks should catch (false survive = 1 - rate).
    """
    from scipy.stats import spearmanr

    base = load_config().attacks
    floor = load_config().evidence.effect_thresholds["spearman_rho"].min
    view = ClaimView(claim_type=ClaimType.CORRELATION, var_x="x", var_y="y",
                     scheme=PermutationScheme.FREE)
    rows = []
    for kind, n, rho in [("true", 60, 0.3), ("true", 100, 0.3), ("true", 200, 0.3),
                         ("true", 100, 0.2), ("no effect", 100, 0.0), ("confounded", 100, 0.0)]:
        for rule in ("point", "interval"):
            config = base.model_copy(update={"break_rule": rule})
            rng = np.random.default_rng(seed + n + int(rho * 100))
            cleared = killed = noisy = 0
            for attempt in range(reps * 30):
                frame = _attack_table(rng, n, "confounded" if kind == "confounded" else "t", rho)
                r_, p_ = spearmanr(frame["x"], frame["y"])
                if not (p_ < 0.05 and abs(r_) >= floor):
                    continue
                results = run_attacks(view, frame, config, seed=attempt)
                cleared += 1
                killed += any(r.outcome.value == "broken" for r in results)
                noisy += any(r.details.get("too_noisy") for r in results)
                if cleared >= reps:
                    break
            rows.append({"scenario": f"{kind}, n={n}, rho={rho}", "kind": "attack_rates",
                         "a2_rule": rule, "gate_cleared": cleared,
                         "share_broken": killed / max(cleared, 1),
                         "share_with_a_too_noisy_check": noisy / max(cleared, 1)})
    return rows


def render_extra(rows: list[dict[str, Any]]) -> str:
    lines = []
    for row in rows:
        if row["kind"] == "family":
            power = "" if row["power"] is None else f" power {row['power']:.2f}"
            lines.append(
                f"family  {row['scenario']:<46} {row['arm']:<5} FDR "
                f"{row['false_discovery_rate']:.3f} any-false {row['any_false_pass']:.3f}{power}"
            )
        else:
            lines.append(f"attacks {row['scenario']:<30} A2={row['a2_rule']:<8} broken "
                         f"{row['share_broken']:.2f} (of {row['gate_cleared']} cleared; "
                         f"too-noisy {row['share_with_a_too_noisy_check']:.2f})")
    return "\n".join(lines)


# --- v2: correlated families through the real gateway, and per-attack kill / survive rates ---
#
# Both parts are measurements only: nothing here changes a verdict or a shipped default.
# The card runs a LABELLED TEST CONFIG: fewer permutations and interval resamples than
# production (`TEST_CONFIG_NOTE`); the production values in configs/verification.yaml are
# untouched.

TEST_CONFIG_NOTE = (
    "test config: template generator, m_max 8, n_permutations and interval_resamples reduced "
    "for speed (descriptive interval only); alpha, bands and attack thresholds are the shipped "
    "ones"
)
ATTACK_IDS = ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a rate; (nan, nan) when nothing was counted."""
    if total <= 0:
        return (math.nan, math.nan)
    p = successes / total
    denom = 1.0 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _family_variant(rng: np.random.Generator, n: int, beta: float, k_true: int,
                    mixed_sign: bool) -> pd.DataFrame:
    """`_family_table`, optionally with null columns that are negatively tied to each other.

    Claims on columns of opposite sign are the case BH's positive-dependence guarantee does
    not cover (docs/RESEARCH_verification_agent.md A2).
    """
    frame = _family_table(rng, n, beta, k_true)
    if mixed_sign:
        for j in (1, 3):
            frame[f"N{j}"] = -frame[f"N{j}"]
    return frame


#: (name, n rows, hub-to-T coefficient, true claims, mixed-sign null columns)
FAMILY_DESIGNS: list[tuple[str, int, float, int, bool]] = [
    ("8 claims, all null, n=100", 100, 0.3, 0, False),
    ("8 claims, all null, mixed-sign columns, n=100", 100, 0.3, 0, True),
    ("8 claims, 3 true (rho about 0.3), n=100", 100, 0.3, 3, False),
    ("8 claims, 3 true (rho about 0.3), n=200", 200, 0.3, 3, False),
    ("8 claims, 3 true (rho about 0.3), mixed-sign nulls, n=200", 200, 0.3, 3, True),
    ("8 claims, 3 true (rho about 0.4), n=100", 100, 0.45, 3, False),
]


def family_config(n_permutations: int, interval_resamples: int) -> VerificationConfig:
    """The labelled test config for family runs (`TEST_CONFIG_NOTE`)."""
    base = pinned_config(n_permutations)
    return base.model_copy(update={"statistics": base.statistics.model_copy(
        update={"m_max": 8, "interval_resamples": interval_resamples})})


def family_replicate(args: tuple[int, int, float, int, bool, int, int, int]) -> dict[str, Any]:
    """One family run through the real gateway: per-claim truth and what each gate stage said.

    Stages: `none` (raw p below alpha), `bh` (q below alpha, what the gate calls significant),
    `holm`, and `pass` (the gateway's final PASS: q, effect floor, direction AND the attacks).
    """
    seed, n, beta, k_true, mixed, n_permutations, interval_resamples, _ = args
    config = family_config(n_permutations, interval_resamples)
    alpha = config.statistics.alpha
    rng = np.random.default_rng(seed)
    claims = _family_claims(k_true)
    frame = _family_variant(rng, n, beta, k_true, mixed)
    proofs = verify_batch([c for c, _ in claims], frame, config, structure=INDEPENDENT)
    p = [pr.p_value if pr.p_value is not None else 1.0 for pr in proofs]
    truth = [t for _, t in claims]
    arms = {
        "none": [v < alpha for v in p],
        "bh": [pr.q_value is not None and pr.q_value < alpha for pr in proofs],
        "holm": _holm(p, alpha),
        "pass": [pr.gate_outcome is GateOutcome.SUPPORTED for pr in proofs],
    }
    broken = [any(a.outcome.value == "broken" for a in pr.attacks) for pr in proofs]
    return {"truth": truth, "arms": arms, "attack_broken": broken}


def summarise_family(
    name: str, k_true: int, reps_out: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Per arm: FDP mean +/- MC standard error, any-false-PASS rate with Wilson interval, power."""
    rows = []
    reps = len(reps_out)
    for arm in ("none", "bh", "holm", "pass"):
        fdp, any_false, power = [], 0, []
        for rep in reps_out:
            rejected, truth = rep["arms"][arm], rep["truth"]
            false = sum(r_ and not t for r_, t in zip(rejected, truth, strict=True))
            total = sum(rejected)
            fdp.append(false / total if total else 0.0)
            any_false += false > 0
            if k_true:
                power.append(sum(r_ and t for r_, t in zip(rejected, truth, strict=True)) / k_true)
        lo, hi = wilson(any_false, reps)
        sd = float(np.std(fdp, ddof=1)) if reps > 1 else math.nan
        row = {"scenario": name, "kind": "family_v2", "arm": arm, "reps": reps,
               "fdp": float(np.mean(fdp)), "fdp_se": sd / math.sqrt(reps),
               "any_false_pass": any_false / reps, "any_false_lo": lo, "any_false_hi": hi,
               "power": float(np.mean(power)) if power else None,
               "power_se": float(np.std(power, ddof=1)) / math.sqrt(reps) if power and reps > 1
               else None}
        rows.append(row)
    return rows


def family_card_v2(reps: int, workers: int = 1, seed: int = 20261025,
                   n_permutations: int = 1000, interval_resamples: int = 200,
                   designs: list[tuple[str, int, float, int, bool]] | None = None
                   ) -> list[dict[str, Any]]:
    """The correlated-family rows: 8 claims sharing columns, real gateway, m_max 8."""
    from concurrent.futures import ProcessPoolExecutor

    rows: list[dict[str, Any]] = []
    for d, (name, n, beta, k_true, mixed) in enumerate(designs or FAMILY_DESIGNS):
        jobs = [(seed + 1000 * d + r, n, beta, k_true, mixed, n_permutations,
                 interval_resamples, r) for r in range(reps)]
        if workers > 1:
            with ProcessPoolExecutor(workers) as pool:
                results = list(pool.map(family_replicate, jobs, chunksize=1))
        else:
            results = [family_replicate(j) for j in jobs]
        rows.extend(summarise_family(name, k_true, results))
        # attacks broken among claims BH called significant: how many luck passes are removed
    return rows


# -- attacks: false-KILL (true effect passes, an attack breaks it) and false-SURVIVE ----------

SHAPES = ["gaussian", "heavy_tail", "skewed", "outliers", "many_columns", "series"]
#: A planted FLAW A2 exists to catch: the link is present only in the last third of the months.
FLAW_SHAPES = ["late_only"]
TRANSACTIONS_MONTHLY = DataStructure(shape=TableShape.TRANSACTIONS, time_column="month",
                                     period="month", entity_column=None, declared_by="caller")


def _spearman_to_pearson(rho: float) -> float:
    """Pearson r of a bivariate normal whose Spearman rho is `rho`."""
    return 2.0 * math.sin(math.pi * rho / 6.0)


def shape_table(shape: str, rng: np.random.Generator, n: int, rho: float) -> pd.DataFrame:
    """A planted table of `shape` with Spearman rho about `rho` between x and y (0 = null).

    Every table also carries a column z tied to x and a three-level `site`, so A3 and A4 have
    something to examine. `series` has one row per month, with the link in the monthly changes.
    """
    r = _spearman_to_pearson(rho)
    x = rng.normal(size=n)
    e = rng.normal(size=n)
    if shape == "late_only":  # `rho` is the link inside the last 4 of 12 months; none before
        month = np.repeat(np.arange(12), math.ceil(n / 12))[:n]
        y = np.where(month >= 8, r * x + math.sqrt(1 - r * r) * e, e)
        start = pd.to_datetime("2021-01-01")
        return pd.DataFrame({"month": start + pd.to_timedelta(month * 31, "D"),
                             "x": x, "y": y, "z": 0.5 * x + 0.87 * rng.normal(size=n),
                             "site": rng.choice(list("abc"), size=n)})
    if shape == "series":
        dx, dy = x, r * x + math.sqrt(1 - r * r) * e
        return pd.DataFrame({"month": pd.date_range("2000-01-01", periods=n, freq="MS"),
                             "x": np.cumsum(dx), "y": np.cumsum(dy)})
    if shape == "heavy_tail":
        e = rng.standard_t(3, size=n) / math.sqrt(3.0)
    y = r * x + math.sqrt(1 - r * r) * e
    if shape == "skewed":
        y = np.exp(0.9 * y)
    if shape == "outliers":
        bad = rng.random(n) < 0.05
        x = np.where(bad, 8.0 * rng.normal(size=n), x)
        y = np.where(bad, 8.0 * rng.normal(size=n), y)
    frame = pd.DataFrame({"x": x, "y": y, "z": 0.5 * x + 0.87 * rng.normal(size=n),
                          "site": rng.choice(list("abc"), size=n)})
    if shape == "many_columns":
        shared = rng.normal(size=n)
        for j in range(8):
            frame[f"w{j}"] = 0.5 * x + 0.4 * shared + 0.7 * rng.normal(size=n)
    return frame


def _stand_in_gate(shape: str, frame: pd.DataFrame, floor: float, alpha: float) -> bool:
    """Spearman p below alpha and |rho| at the floor: the gate for a family of ONE claim.

    This is a stand-in, not the gateway: it skips the sandbox, the 50/50 split and BH, so
    thousands of tables can be tried. `cross_check_stand_in` compares it with the real gateway.
    """
    from scipy.stats import spearmanr

    if shape == "series":
        a, b = np.diff(frame["x"].to_numpy()), np.diff(frame["y"].to_numpy())
    else:
        a, b = frame["x"].to_numpy(), frame["y"].to_numpy()
    r_, p_ = spearmanr(a, b)
    return bool(p_ < alpha and abs(r_) >= floor)


def attack_cell(
    args: tuple[str, int, float, int, int, int, int, tuple[str, ...]],
) -> dict[str, Any]:
    """Tables of one shape/n/rho that clear the stand-in gate, attacked under BOTH A2 rules.

    Both rules see the very same tables and seeds, so their difference is paired.
    """
    shape, n, rho, reps, seed, cap_factor, damage_resamples, arms = args
    base = load_config()
    floor = base.evidence.effect_thresholds["spearman_rho"].min
    alpha = base.statistics.alpha
    cfgs = {arm: base.attacks.model_copy(update={
                "break_rule": arm.split("@")[0], "damage_resamples": damage_resamples,
                **({"false_kill_budget": float(arm.split("@")[1])} if "@" in arm else {})})
            for arm in arms}
    min_capacity = base.attacks.min_capacity
    scheme = (PermutationScheme.BLOCK_DIFFERENCED if shape == "series"
              else PermutationScheme.STRATIFIED if shape == "late_only" else PermutationScheme.FREE)
    structure = (SERIES if shape == "series"
                 else TRANSACTIONS_MONTHLY if shape == "late_only" else INDEPENDENT)
    view = ClaimView(claim_type=ClaimType.CORRELATION, var_x="x", var_y="y", scheme=scheme)
    rng = np.random.default_rng(seed)
    out: dict[str, Any] = {"shape": shape, "n": n, "rho": rho, "attempts": 0, "cleared": 0,
                           "rules": {r: {"broken": {a: 0 for a in ATTACK_IDS}, "any_broken": 0,
                                         "a2_too_noisy": 0, "little_checked": 0,
                                         "checks_ran": 0, "could_not_tell": 0}
                                     for r in cfgs}}
    while out["cleared"] < reps and out["attempts"] < reps * cap_factor:
        out["attempts"] += 1
        frame = shape_table(shape, rng, n, rho)
        if not _stand_in_gate(shape, frame, floor, alpha):
            continue
        out["cleared"] += 1
        framed = with_period_column(frame, structure)
        attack_seed = int(rng.integers(1 << 30))
        for rule, cfg in cfgs.items():
            results = run_attacks(view, framed, cfg, seed=attack_seed)
            acc = out["rules"][rule]
            for res in results:
                acc["broken"][res.attack_id] += res.outcome.value == "broken"
            acc["any_broken"] += any(res.outcome.value == "broken" for res in results)
            acc["a2_too_noisy"] += any(res.attack_id == "A2" and res.details.get("too_noisy")
                                       for res in results)
            ran = sum(res.outcome.value != "not_run" for res in results)
            acc["checks_ran"] += ran
            acc["little_checked"] += ran < min_capacity
            acc["could_not_tell"] += sum(res.outcome.value == "not_run" and res.applicable
                                         for res in results)
    return out


#: (shape, n, rho) cells: the planted shapes at n 60 / 120 / 300 and rho 0.2 / 0.3, plus nulls.
def attack_cells() -> list[tuple[str, int, float]]:
    cells: list[tuple[str, int, float]] = []
    for shape in SHAPES:
        for n in (60, 120, 300):
            for rho in (0.2, 0.3, 0.0):
                cells.append((shape, n, rho))
    return cells


def flaw_cells() -> list[tuple[str, int, float]]:
    """The planted late-period-only link (rho 0.7 inside the last third) at n 60 / 120 / 300."""
    return [("late_only", n, 0.7) for n in (60, 120, 300)]


def attack_card_v2(reps: int, workers: int = 1, seed: int = 20261027,
                   cells: list[tuple[str, int, float]] | None = None,
                   cap_factor: int = 60, damage_resamples: int = 300,
                   arms: tuple[str, ...] = ("point", "interval")) -> list[dict[str, Any]]:
    """Per-cell counts of broken checks: true effects (false kill) and luck passes (false survive).

    `damage_resamples` is 300 here (production 1000) so the interval rule costs about a second
    a table, not three; `--v2 attacks` documents this as part of the labelled test config.
    """
    from concurrent.futures import ProcessPoolExecutor

    jobs = [(shape, n, rho, reps, seed + 7919 * i, cap_factor, damage_resamples, arms)
            for i, (shape, n, rho) in enumerate(cells or attack_cells())]
    if workers > 1:
        with ProcessPoolExecutor(workers) as pool:
            return list(pool.map(attack_cell, jobs, chunksize=1))
    return [attack_cell(j) for j in jobs]


def cross_check_stand_in(reps: int, seed: int = 20261028) -> dict[str, Any]:
    """Real gateway vs the stand-in on one cell (gaussian, 120 rows, rho 0.3): clear and kill rates.

    `verify_batch` tests the rows it is handed (the product hands it the confirmation half), so
    both arms see 120 rows. `gateway_fragile` counts cleared claims that an attack then broke.
    """
    config = pinned_config(1000)
    config = config.model_copy(update={"statistics": config.statistics.model_copy(
        update={"interval_resamples": 200})})
    rng = np.random.default_rng(seed)
    claim = _claim(ClaimType.CORRELATION, ["x", "y"], None)
    cleared = broken = 0
    floor = config.evidence.effect_thresholds["spearman_rho"].min
    stand_in = stand_broken = 0
    view = ClaimView(claim_type=ClaimType.CORRELATION, var_x="x", var_y="y",
                     scheme=PermutationScheme.FREE)
    for i in range(reps):
        frame = shape_table("gaussian", rng, 120, 0.3)
        proof = verify_batch([claim], frame, config, structure=INDEPENDENT)[0]
        if proof.q_value is not None and proof.q_value < config.statistics.alpha and \
                proof.effect_size is not None and abs(proof.effect_size) >= floor:
            cleared += 1
            broken += proof.gate_outcome is GateOutcome.FRAGILE
        again = shape_table("gaussian", rng, 120, 0.3)
        if _stand_in_gate("gaussian", again, floor, config.statistics.alpha):
            stand_in += 1
            res = run_attacks(view, again, config.attacks, seed=i)
            stand_broken += any(r.outcome.value == "broken" for r in res)
    return {"reps": reps, "gateway_cleared": cleared, "gateway_fragile": broken,
            "stand_in_cleared": stand_in, "stand_in_broken": stand_broken}


def _fmt_rate(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return "n/a" if n == 0 else f"{k / n:.3f} [{lo:.3f}, {hi:.3f}]"


def render_attack_v2(cells: list[dict[str, Any]]) -> str:
    """Markdown: per cell, the share of gate-clearing tables any check broke, per A2 arm."""
    arms = list(cells[0]["rules"]) if cells else []
    lines = ["| kind | shape | n | rho | cleared / tried | " + " | ".join(
        f"any broken, A2 {a}" for a in arms) + " | A2 noisy (" + (arms[1] if len(arms) > 1 else "-")
        + ") |", "|" + "---|" * (6 + len(arms) - 1)]
    for c in cells:
        kind = "luck-pass (null)" if c["rho"] == 0 else ("planted flaw" if c["shape"] in FLAW_SHAPES
                                                         else "true effect")
        k = c["cleared"]
        noisy = c["rules"][arms[1]]["a2_too_noisy"] if len(arms) > 1 else 0
        lines.append(f"| {kind} | {c['shape']} | {c['n']} | {c['rho']} | {k}/{c['attempts']} | "
                     + " | ".join(_fmt_rate(c["rules"][a]["any_broken"], k) for a in arms)
                     + f" | {_fmt_rate(noisy, k)} |")
    return "\n".join(lines)


def pooled_attack_rows(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pool cells into (kind, arm) rows with per-attack breaks, checks run and cleared counts."""
    rows = []
    arms = list(cells[0]["rules"]) if cells else []
    for kind, picker in (("true", lambda c: c["rho"] > 0 and c["shape"] not in FLAW_SHAPES),
                         ("null", lambda c: c["rho"] == 0),
                         ("flaw", lambda c: c["shape"] in FLAW_SHAPES)):
        chosen = [c for c in cells if picker(c)]
        if not chosen:
            continue
        for arm in arms:
            total = sum(c["cleared"] for c in chosen)
            per = {a: sum(c["rules"][arm]["broken"][a] for c in chosen) for a in ATTACK_IDS}
            rows.append({"kind": kind, "a2_rule": arm, "cleared": total,
                         "any_broken": sum(c["rules"][arm]["any_broken"] for c in chosen),
                         "checks_ran": sum(c["rules"][arm]["checks_ran"] for c in chosen),
                         "per_attack": per})
    return rows


def render(card: dict[str, Any]) -> str:
    lines = [f"alpha {card['alpha']}, {card['n_permutations']} permutations, "
             f"{card['reps']} replicates per row", ""]
    for row in card["rows"]:
        rate = row.get("rate_q_below_alpha", row.get("rate_any_attack_broken"))
        lines.append(f"{row['kind']:<15} {row['scenario']:<44} {rate:6.3f} +/- "
                     f"{row['standard_error']:.3f}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=100)
    parser.add_argument("--permutations", type=int, default=1000)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--v2", default=None,
                        choices=["families", "attacks", "flaws", "sensitivity", "cross-check"],
                        help="v2 rows: correlated families (real gateway), per-attack "
                        "false-kill / false-survive rates, or the stand-in cross-check")
    parser.add_argument("--workers", type=int, default=1, help="processes for --v2")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--extra", action="store_true",
                        help="correlated family of 8 and attack false-kill / false-survive rows")
    args = parser.parse_args()
    if args.v2:
        if args.v2 == "families":
            data = family_card_v2(args.reps, args.workers, n_permutations=args.permutations,
                                  **({} if args.seed is None else {"seed": args.seed}))
        elif args.v2 == "attacks":
            data = attack_card_v2(args.reps, args.workers,
                                  **({} if args.seed is None else {"seed": args.seed}))
            print(render_attack_v2(data))
        elif args.v2 in ("flaws", "sensitivity"):
            cells = flaw_cells() if args.v2 == "flaws" else [
                ("gaussian", n, rho) for n in (60, 120, 300) for rho in (0.2, 0.3, 0.0)]
            data = attack_card_v2(args.reps, args.workers, cells=cells,
                                  seed=(args.seed or 20261029),
                                  arms=("point", "interval", "interval@0.2", "interval@0.4"))
            print(render_attack_v2(data))
        else:
            data = cross_check_stand_in(args.reps)
        print(json.dumps(data, indent=1)[:4000] if args.v2 in ("families", "cross-check") else "")
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return
    if args.extra:
        extra = family_card(args.reps, n_permutations=args.permutations) + attack_card(args.reps)
        print(render_extra(extra))
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(extra, indent=2) + "\n", encoding="utf-8")
        return
    card = report_card(args.reps, n_permutations=args.permutations)
    print(render(card))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
