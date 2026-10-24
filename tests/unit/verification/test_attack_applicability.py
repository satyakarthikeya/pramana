"""S3: an attack that cannot apply says so, and never counts as survived or broken."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.contracts import AttackOutcome, ClaimType, DataStructure, PermutationScheme
from pramana.contracts import Direction, GateOutcome
from pramana.verification.attacks import ClaimView, run_attacks
from pramana.verification.gateway import verify_batch
from pramana.verification.schemes import with_period_column
from tests.fixtures.candidates import candidate
from tests.fixtures.config import load_pinned_config

CONFIG = load_pinned_config()


def _rows(n: int = 240, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    return with_period_column(
        pd.DataFrame(
            {
                "x": x,
                "y": 0.6 * x + rng.normal(size=n),
                "z": rng.normal(size=n),
                "group": rng.choice(["a", "b", "c"], n),
            }
        ),
        DataStructure.independent_rows(),
    )


def _by_id(claim: ClaimView, rows: pd.DataFrame) -> dict:
    return {r.attack_id: r for r in run_attacks(claim, rows, CONFIG.attacks, seed=1)}


def test_every_result_says_whether_the_attack_could_apply() -> None:
    results = _by_id(
        ClaimView(ClaimType.CORRELATION, "x", "y", PermutationScheme.FREE), _rows()
    )
    assert list(results) == [f"A{i}" for i in range(1, 8)]
    # independent rows: no time order to detrend (A6) and no third variable tied to both sides (A3)
    not_applicable = {k for k, v in results.items() if not v.applicable}
    assert not_applicable == {"A3", "A6"}, {k: results[k].reason for k in not_applicable}
    assert all(results[k].outcome is not AttackOutcome.NOT_RUN for k in ("A1", "A2", "A4", "A5", "A7"))


def test_a_claim_type_with_no_attack_is_not_applicable_to_all_seven() -> None:
    for claim_type in (ClaimType.PERIOD_CHANGE, ClaimType.SEASONALITY):
        results = run_attacks(
            ClaimView(claim_type, "x", "y", PermutationScheme.PAIRED), _rows(), CONFIG.attacks, seed=1
        )
        assert len(results) == 7
        assert all(r.outcome is AttackOutcome.NOT_RUN and not r.applicable for r in results)


def test_structural_reasons_are_not_applicable() -> None:
    rows = _rows()
    trend = _by_id(ClaimView(ClaimType.TREND, "x", "y", PermutationScheme.FREE), rows)
    assert trend["A3"].outcome is AttackOutcome.NOT_RUN and not trend["A3"].applicable
    group = _by_id(ClaimView(ClaimType.GROUP_DIFFERENCE, "group", "y", PermutationScheme.FREE), rows)
    assert not group["A6"].applicable and not group["A7"].applicable
    unsigned = _by_id(
        ClaimView(ClaimType.GROUP_DIFFERENCE, "group", "y", PermutationScheme.FREE, unsigned=True),
        rows,
    )
    assert not unsigned["A5"].applicable and not unsigned["A4"].applicable


def test_a_table_too_small_to_run_an_attack_is_still_applicable() -> None:
    results = _by_id(
        ClaimView(ClaimType.CORRELATION, "x", "y", PermutationScheme.FREE), _rows(n=40)
    )
    too_small = [results["A2"], results["A4"]]  # "each half needs 30 rows", "no subgroup has 30 rows"
    assert all(r.outcome is AttackOutcome.NOT_RUN and r.applicable for r in too_small), [
        (r.attack_id, r.reason, r.applicable) for r in too_small
    ]


def test_not_run_is_never_counted_as_survived() -> None:
    from pramana.api.v1 import rejection_reason

    rows = _rows()
    claim = ClaimView(ClaimType.CORRELATION, "x", "y", PermutationScheme.FREE)
    results = list(run_attacks(claim, rows, CONFIG.attacks, seed=1))
    survived = sum(r.outcome is AttackOutcome.SURVIVED for r in results)
    ran = sum(r.outcome is not AttackOutcome.NOT_RUN for r in results)
    assert survived <= ran <= 7
    # the wording quotes the same counts
    proof = verify_batch(
        [candidate("c", "y is positively associated with x", ClaimType.CORRELATION, ["x", "y"],
                   direction=Direction.POSITIVE)],
        rows, CONFIG,
    )[0]
    if proof.gate_outcome is GateOutcome.SUPPORTED:
        text = rejection_reason(proof)
        ran_p = sum(a.outcome is not AttackOutcome.NOT_RUN for a in proof.attacks)
        assert f" of {ran_p} further checks" in text


def test_attacks_never_run_on_a_claim_the_gate_rejected() -> None:
    rng = np.random.default_rng(8)
    frame = pd.DataFrame({"x": rng.normal(size=80), "y": rng.normal(size=80)})
    proof = verify_batch(
        [candidate("n", "y is positively associated with x", ClaimType.CORRELATION, ["x", "y"],
                   direction=Direction.POSITIVE)],
        frame, CONFIG,
    )[0]
    assert proof.verdict.value == "REJECT" and proof.attacks == []
