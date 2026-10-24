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
    parser.add_argument("--extra", action="store_true",
                        help="correlated family of 8 and attack false-kill / false-survive rows")
    args = parser.parse_args()
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
