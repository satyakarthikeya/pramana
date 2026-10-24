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
    args = parser.parse_args()
    card = report_card(args.reps, n_permutations=args.permutations)
    print(render(card))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
