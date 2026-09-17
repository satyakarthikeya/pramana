"""The acceptance test (SCOPE.md 6) -- the whole gateway on one toy dataset.

This is the test that mirrors the live demo, and it is the one that must never be
deleted or skipped (tests/OWNERSHIP.md). It asserts the product promise directly:

    the planted true relationship survives, the planted false correlation dies,
    every claim carries a complete proof object, and nothing REJECTed reaches memory.

It runs the real subprocess executor against the real templates -- no mocks anywhere
in the statistical path. `n_permutations` is lowered so the suite stays usable; the
p-value floor moves with it and nothing else changes.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pramana.contracts.enums import GateOutcome, Verdict
from pramana.verification.config import VerificationConfig, load_config
from pramana.verification.gateway import verify_batch
from pramana.verification.memory_guard import writable
from tests.fixtures import demo_batch, toy_frame

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def config() -> VerificationConfig:
    """The shipped config with a smaller permutation budget.

    1000 permutations puts the p-value floor at 1/1001, comfortably below alpha, so
    the planted effects can still clear BH with room to spare.
    """
    shipped = load_config()
    return shipped.model_copy(
        update={"statistics": shipped.statistics.model_copy(update={"n_permutations": 1000})}
    )


@pytest.fixture(scope="module")
def proofs(config: VerificationConfig) -> dict[str, object]:
    frame: pd.DataFrame = toy_frame()
    results = verify_batch(demo_batch(), frame, config)
    return {proof.insight_id: proof for proof in results}


def test_every_candidate_gets_exactly_one_proof_object(config: VerificationConfig) -> None:
    batch = demo_batch()
    results = verify_batch(batch, toy_frame(), config)
    assert [proof.insight_id for proof in results] == [c.insight_id for c in batch]


# --- the promise ----------------------------------------------------------


def test_planted_true_correlation_passes(proofs: dict) -> None:
    proof = proofs["c-true-correlation"]
    assert proof.verdict is Verdict.PASS
    assert proof.gate_outcome is GateOutcome.SUPPORTED
    assert proof.effect_size > 0.3, "the planted rho is ~0.42; a much smaller value means "
    assert proof.evidence_score is not None


def test_planted_false_correlation_is_rejected(proofs: dict) -> None:
    """`decoy` is a shuffled copy of `bmi`: same marginal, zero association.

    This is the single most important assertion in the repo. If it ever fails, the
    gate is passing a fabricated finding and the product claim is false.
    """
    proof = proofs["c-false-correlation"]
    assert proof.verdict is Verdict.REJECT
    assert proof.gate_outcome in {GateOutcome.INCONCLUSIVE, GateOutcome.NEGLIGIBLE}
    assert proof.evidence_score is None


def test_pure_noise_pair_is_rejected(proofs: dict) -> None:
    assert proofs["c-null-correlation"].verdict is Verdict.REJECT


def test_planted_group_difference_passes(proofs: dict) -> None:
    proof = proofs["c-true-group"]
    assert proof.verdict is Verdict.PASS
    assert proof.effect_size > 0.0, "reference_group='urban' puts urban first, so a "
    "positive delta means urban sits higher -- which is what the claim says"


def test_planted_trend_passes(proofs: dict) -> None:
    assert proofs["c-true-trend"].verdict is Verdict.PASS


def test_null_trend_and_null_group_are_rejected(proofs: dict) -> None:
    assert proofs["c-null-trend"].verdict is Verdict.REJECT
    assert proofs["c-null-group"].verdict is Verdict.REJECT


def test_claim_asserting_the_wrong_direction_is_refuted(proofs: dict) -> None:
    """Same columns as the passing claim, opposite asserted direction.

    Without the direction check this would PASS on a strong effect pointing the other
    way, which is how "X falls with Y" gets reported from data showing a rise.
    """
    proof = proofs["c-wrong-direction"]
    assert proof.gate_outcome is GateOutcome.REFUTED
    assert proof.verdict is Verdict.REJECT


# --- screened-out claims --------------------------------------------------


@pytest.mark.parametrize(
    "insight_id",
    ["c-universal", "c-causal", "c-distribution", "c-missing-column", "c-wrong-arity"],
)
def test_inadmissible_claims_are_not_testable(proofs: dict, insight_id: str) -> None:
    proof = proofs[insight_id]
    assert proof.gate_outcome is GateOutcome.NOT_TESTABLE
    assert proof.verdict is Verdict.REJECT
    assert proof.failure_reason, "a refused claim must say why, so the agent can revise"
    assert proof.p_value is None and proof.q_value is None
    assert proof.falsification_code is None, "nothing was generated, nothing ran"


def test_screened_out_claims_are_excluded_from_the_bh_family(proofs: dict) -> None:
    """The family is the TESTED set. Counting refusals would inflate the correction
    and make every real claim harder to pass for no statistical reason.
    """
    tested = [p for p in proofs.values() if p.gate_outcome is not GateOutcome.NOT_TESTABLE]
    screened = [p for p in proofs.values() if p.gate_outcome is GateOutcome.NOT_TESTABLE]
    assert len(tested) == 8 and len(screened) == 5
    assert {p.n_hypotheses_in_batch for p in tested} == {8}


def test_one_family_id_for_the_whole_run(proofs: dict) -> None:
    assert len({p.bh_family_id for p in proofs.values()}) == 1


# --- proof objects and the memory guard -----------------------------------


def test_tested_claims_carry_complete_proof_objects(proofs: dict) -> None:
    for proof in proofs.values():
        if proof.gate_outcome is GateOutcome.NOT_TESTABLE:
            continue
        assert proof.p_value is not None and 0.0 < proof.p_value <= 1.0
        assert proof.q_value is not None and proof.q_value >= proof.p_value
        assert proof.effect_metric is not None
        assert proof.falsification_code, "the audit trail is the code that actually ran"
        assert proof.seed is not None


def test_only_passed_insights_reach_memory(proofs: dict) -> None:
    """AGENTS.md 0, end to end: memory_write => verdict == PASS."""
    accepted = writable(list(proofs.values()))
    assert accepted, "the toy frame has real signal; something should have passed"
    assert all(proof.verdict is Verdict.PASS for proof in accepted)
    assert all(proof.gate_outcome is GateOutcome.SUPPORTED for proof in accepted)
    rejected_ids = {p.insight_id for p in proofs.values() if p.verdict is Verdict.REJECT}
    assert not ({p.insight_id for p in accepted} & rejected_ids)


def test_run_is_reproducible(config: VerificationConfig) -> None:
    """Same seed, same data, same verdicts. Without this, a proof object proves nothing
    about the next run (AGENTS.md 3.4).
    """
    frame = toy_frame()
    first = verify_batch(demo_batch(), frame, config)
    second = verify_batch(demo_batch(), frame, config)
    assert [(p.insight_id, p.p_value, p.q_value) for p in first] == [
        (p.insight_id, p.p_value, p.q_value) for p in second
    ]
