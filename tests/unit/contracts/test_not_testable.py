"""`NOT_TESTABLE` and the nullability rule on `ProofObject`.

The rule is "null exactly when the claim was never tested", and both halves are
load-bearing:

  * a NUMBER on a screened-out claim would be fabricated -- nothing computed it;
  * a NULL on a tested claim would be a proof object with a hole in it, and
    AGENTS.md 3.6 says there is no such thing as a partial proof object.

Pydantic enforces both directions, so neither can be introduced by a caller that
forgets.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pramana.contracts.enums import EffectMetric, GateOutcome, TestType, Verdict
from pramana.contracts.proof_object import ProofObject

STATISTICAL_FIELDS = {
    "p_value": 0.01,
    "q_value": 0.04,
    "effect_size": 0.42,
    "effect_metric": EffectMetric.SPEARMAN_RHO,
    "test_type": TestType.PERMUTATION,
    "falsification_code": "# generated",
    "n_hypotheses_in_batch": 8,
}


def _screened_out(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "insight_id": "c-screened",
        "verdict": Verdict.REJECT,
        "gate_outcome": GateOutcome.NOT_TESTABLE,
        "bh_family_id": "bh-abc",
        "failure_reason": "claim uses universal wording ['always']",
        "seed": 1,
    }
    payload.update(overrides)
    return payload


def _tested(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "insight_id": "c-tested",
        "verdict": Verdict.REJECT,
        "gate_outcome": GateOutcome.INCONCLUSIVE,
        "bh_family_id": "bh-abc",
        "seed": 1,
        **STATISTICAL_FIELDS,
    }
    payload.update(overrides)
    return payload


# --- the enum -------------------------------------------------------------


def test_not_testable_maps_to_reject() -> None:
    proof = ProofObject.model_validate(_screened_out())
    assert proof.verdict is Verdict.REJECT


def test_not_testable_cannot_be_a_pass() -> None:
    """The one thing that must be impossible: a claim we could not test, marked PASS."""
    with pytest.raises(ValidationError, match="contradicts gate_outcome"):
        ProofObject.model_validate(_screened_out(verdict=Verdict.PASS))


# --- null exactly when untested -------------------------------------------


def test_screened_out_claim_has_no_statistics() -> None:
    proof = ProofObject.model_validate(_screened_out())
    assert proof.p_value is None
    assert proof.q_value is None
    assert proof.effect_size is None
    assert proof.effect_metric is None
    assert proof.test_type is None
    assert proof.falsification_code is None
    assert proof.n_hypotheses_in_batch is None


@pytest.mark.parametrize("field,value", sorted(STATISTICAL_FIELDS.items(), key=lambda kv: kv[0]))
def test_any_statistic_on_a_screened_out_claim_is_refused(field: str, value: object) -> None:
    """Including a p_value of 1.0 or an effect_size of 0.0: a conservative-looking
    number is still a number nothing computed.
    """
    with pytest.raises(ValidationError, match="must be null"):
        ProofObject.model_validate(_screened_out(**{field: value}))


@pytest.mark.parametrize("field", sorted(STATISTICAL_FIELDS))
def test_any_missing_statistic_on_a_tested_claim_is_refused(field: str) -> None:
    with pytest.raises(ValidationError, match="must be populated"):
        ProofObject.model_validate(_tested(**{field: None}))


def test_screened_out_claim_must_say_why() -> None:
    """The reason is what the analysis agent needs in order to rewrite the claim."""
    with pytest.raises(ValidationError, match="failure_reason"):
        ProofObject.model_validate(_screened_out(failure_reason=None))


def test_screened_out_claim_still_names_the_family_it_was_excluded_from() -> None:
    assert ProofObject.model_validate(_screened_out()).bh_family_id == "bh-abc"


# --- the crashed-test case, which is NOT the same shape -------------------


def test_crashed_test_keeps_its_code_and_stays_in_the_family() -> None:
    """A crash is not a screening. Code was generated and did run, so the audit trail
    exists, the claim counts toward the family, and the p-value is the most
    conservative one available rather than absent.
    """
    proof = ProofObject.model_validate(
        _tested(
            p_value=1.0,
            q_value=1.0,
            effect_size=0.0,
            failure_reason="execution exceeded the 60s timeout and was killed",
        )
    )
    assert proof.gate_outcome is GateOutcome.INCONCLUSIVE
    assert proof.verdict is Verdict.REJECT
    assert proof.falsification_code, "the code that failed is still the audit trail"
    assert proof.n_hypotheses_in_batch == 8
    assert proof.evidence_score is None
