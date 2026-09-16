"""Gateway batch mechanics: ordering, family membership, and the edges.

The statistical behaviour is covered by the acceptance test
(`tests/integration/test_gateway_e2e.py`). These are the cases that are cheap to test
because they never reach the executor -- and the ones most likely to be got wrong
quietly, since none of them changes a p-value.
"""

from __future__ import annotations

import pytest

from pramana.contracts.enums import GateOutcome, Verdict
from pramana.verification.config import VerificationConfig, load_config
from pramana.verification.gateway import verify_batch
from tests.fixtures.candidates import (
    INADMISSIBLE_CANDIDATES,
    UNIVERSAL_CLAIM,
    candidate,
)
from tests.fixtures.frames import toy_frame


@pytest.fixture(scope="module")
def config() -> VerificationConfig:
    shipped = load_config()
    return shipped.model_copy(
        update={"statistics": shipped.statistics.model_copy(update={"n_permutations": 1000})}
    )


@pytest.fixture(scope="module")
def frame():
    return toy_frame(n_rows=60)


def test_batch_of_only_inadmissible_claims_returns_cleanly(config, frame) -> None:
    """An empty BH family is a legitimate run, not a crash: every candidate was
    refused before testing, so there is nothing to correct.
    """
    proofs = verify_batch(INADMISSIBLE_CANDIDATES, frame, config)
    assert len(proofs) == len(INADMISSIBLE_CANDIDATES)
    assert all(proof.gate_outcome is GateOutcome.NOT_TESTABLE for proof in proofs)
    assert all(proof.verdict is Verdict.REJECT for proof in proofs)
    assert all(proof.n_hypotheses_in_batch is None for proof in proofs)


def test_empty_batch_returns_empty(config, frame) -> None:
    assert verify_batch([], frame, config) == []


def test_output_order_matches_input_order(config, frame) -> None:
    """Callers zip proofs against candidates. A reordering here would silently attach
    every verdict to the wrong claim.
    """
    batch = list(reversed(INADMISSIBLE_CANDIDATES))
    proofs = verify_batch(batch, frame, config)
    assert [p.insight_id for p in proofs] == [c.insight_id for c in batch]


def test_duplicate_insight_ids_are_refused(config, frame) -> None:
    """Proof objects are keyed on `insight_id`; a duplicate would overwrite a verdict
    rather than report two.
    """
    twice = [UNIVERSAL_CLAIM, UNIVERSAL_CLAIM]
    with pytest.raises(ValueError, match="unique within a run"):
        verify_batch(twice, frame, config)


def test_family_id_is_stable_for_the_same_set(config, frame) -> None:
    first = verify_batch(INADMISSIBLE_CANDIDATES, frame, config)
    second = verify_batch(INADMISSIBLE_CANDIDATES, frame, config)
    assert {p.bh_family_id for p in first} == {p.bh_family_id for p in second}


def test_refusal_reason_reaches_the_proof_object(config, frame) -> None:
    """The agent revises from this string, so it has to name the actual problem."""
    proofs = verify_batch([UNIVERSAL_CLAIM], frame, config)
    assert "universal wording" in (proofs[0].failure_reason or "")


def test_unknown_columns_are_refused_rather_than_crashing_the_executor(config, frame) -> None:
    ghost = candidate(
        "c-ghost", "ghost is associated with age", UNIVERSAL_CLAIM.claim_type, ["age", "ghost"]
    )
    proof = verify_batch([ghost], frame, config)[0]
    assert proof.gate_outcome is GateOutcome.NOT_TESTABLE
    assert "ghost" in (proof.failure_reason or "")
