"""Memory guard tests -- the prime directive, `memory_write => verdict == PASS`.

`tests/OWNERSHIP.md` lists this among the tests that must never be deleted or skipped.
The function is ten lines; the reason it gets this much test is that it is the single
narrowest point in the system, and every other module's correctness is irrelevant if
this one lets something through.
"""

from __future__ import annotations

import pytest

from pramana.contracts.enums import EffectMetric, GateOutcome, TestType, Verdict
from pramana.contracts.proof_object import ProofObject, ScoreComponents
from pramana.verification.memory_guard import MemoryWriteRefused, assert_writable, writable


def _proof(insight_id: str, outcome: GateOutcome) -> ProofObject:
    supported = outcome is GateOutcome.SUPPORTED
    if outcome is GateOutcome.NOT_TESTABLE:
        return ProofObject(
            insight_id=insight_id,
            verdict=Verdict.REJECT,
            gate_outcome=outcome,
            bh_family_id="bh-test",
            failure_reason="screened out",
            seed=1,
        )
    return ProofObject(
        insight_id=insight_id,
        verdict=Verdict.PASS if supported else Verdict.REJECT,
        p_value=0.001,
        q_value=0.004,
        effect_size=0.42,
        evidence_score=0.6 if supported else None,
        score_components=ScoreComponents(s_q=0.6, s_e=0.6, s_r=1.0) if supported else None,
        test_type=TestType.PERMUTATION,
        falsification_code="# generated",
        n_hypotheses_in_batch=4,
        gate_outcome=outcome,
        effect_metric=EffectMetric.SPEARMAN_RHO,
        bh_family_id="bh-test",
        seed=1,
    )


def test_supported_insight_is_returned_unchanged() -> None:
    proof = _proof("ok", GateOutcome.SUPPORTED)
    assert assert_writable(proof) is proof


@pytest.mark.parametrize(
    "outcome",
    [
        GateOutcome.REFUTED,
        GateOutcome.NEGLIGIBLE,
        GateOutcome.INCONCLUSIVE,
        GateOutcome.NOT_TESTABLE,
    ],
)
def test_every_non_supported_outcome_is_refused(outcome: GateOutcome) -> None:
    """Including NOT_TESTABLE. A claim we could not even test is the LAST thing that
    should reach long-term memory.
    """
    with pytest.raises(MemoryWriteRefused) as raised:
        assert_writable(_proof("bad", outcome))
    assert raised.value.insight_id == "bad"
    assert raised.value.gate_outcome is outcome


def test_refusal_raises_rather_than_returning_false() -> None:
    """A boolean invites `if guard(proof):` with a forgotten else branch, and a
    forgotten else branch is a silent write of unverified material.
    """
    with pytest.raises(MemoryWriteRefused):
        assert_writable(_proof("bad", GateOutcome.INCONCLUSIVE))


def test_refusal_is_not_a_value_error() -> None:
    """So a generic `except ValueError` upstream cannot swallow a breach attempt."""
    error = MemoryWriteRefused(_proof("bad", GateOutcome.REFUTED))
    assert isinstance(error, RuntimeError)
    assert not isinstance(error, ValueError)


def test_refusal_message_names_the_insight_and_the_outcome() -> None:
    with pytest.raises(MemoryWriteRefused, match="bad-1.*REJECT.*REFUTED"):
        assert_writable(_proof("bad-1", GateOutcome.REFUTED))


def test_writable_filters_a_mixed_batch_in_order() -> None:
    batch = [
        _proof("a", GateOutcome.SUPPORTED),
        _proof("b", GateOutcome.REFUTED),
        _proof("c", GateOutcome.SUPPORTED),
        _proof("d", GateOutcome.NOT_TESTABLE),
        _proof("e", GateOutcome.INCONCLUSIVE),
    ]
    assert [proof.insight_id for proof in writable(batch)] == ["a", "c"]


def test_writable_of_an_all_rejected_batch_is_empty() -> None:
    """A run where nothing passes is a legitimate outcome, not an error."""
    batch = [_proof("a", GateOutcome.INCONCLUSIVE), _proof("b", GateOutcome.NEGLIGIBLE)]
    assert writable(batch) == []


def test_every_proof_writable_accepts_would_also_pass_assert_writable() -> None:
    """The two entry points must never disagree about what may be written."""
    batch = [_proof(str(index), outcome) for index, outcome in enumerate(GateOutcome)]
    for proof in writable(batch):
        assert assert_writable(proof) is proof
