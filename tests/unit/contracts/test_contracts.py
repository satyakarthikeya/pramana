"""Contract tests (SCOPE.md 4 step 1, PROJECT.md 5).

Other modules import these models, so their guarantees are pinned here. The
verdict/outcome invariant is the prime directive in executable form (AGENTS.md 0).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pramana.contracts import (
    CandidateInsight,
    ClaimType,
    Direction,
    EffectMetric,
    GateOutcome,
    ProofObject,
    ScoreComponents,
    TestType,
    Verdict,
)


def _proof(**overrides: object) -> ProofObject:
    fields: dict[str, object] = {
        "insight_id": "ins-001",
        "verdict": Verdict.PASS,
        "p_value": 0.0004,
        "q_value": 0.004,
        "effect_size": 0.42,
        "evidence_score": 0.61,
        "test_type": TestType.PERMUTATION,
        "falsification_code": "from pramana.verification.stats import permutation_test",
        "n_hypotheses_in_batch": 12,
        "gate_outcome": GateOutcome.SUPPORTED,
        "effect_metric": EffectMetric.SPEARMAN_RHO,
        "bh_family_id": "run-2026-08-19-a",
        "seed": 20260817,
    }
    fields.update(overrides)
    return ProofObject(**fields)  # type: ignore[arg-type]


# --- CandidateInsight -----------------------------------------------------


def test_candidate_round_trips() -> None:
    original = CandidateInsight(
        insight_id="ins-001",
        claim="systolic blood pressure rises with age",
        claim_type=ClaimType.CORRELATION,
        variables=["age", "sbp"],
        dataset_ref="data/interim/nhanes.parquet",
        analysis_evidence={"stat": "pearson_r", "raw_value": 0.31},
        asserted_direction=Direction.POSITIVE,
    )
    restored = CandidateInsight.model_validate_json(original.model_dump_json())
    assert restored == original


def test_direction_defaults_to_none_so_upstream_stays_valid() -> None:
    """asserted_direction is additive: a producer that does not set it must not break."""
    insight = CandidateInsight(
        insight_id="ins-002",
        claim="income differs by region",
        claim_type=ClaimType.GROUP_DIFFERENCE,
        variables=["region", "income"],
        dataset_ref="d.parquet",
    )
    assert insight.asserted_direction is None
    assert insight.analysis_evidence == {}


def test_all_four_claim_types_from_the_contract_are_accepted() -> None:
    for claim_type in ("correlation", "group_difference", "trend", "distribution"):
        insight = CandidateInsight(
            insight_id="i",
            claim="c",
            claim_type=claim_type,  # type: ignore[arg-type]
            variables=["a"],
            dataset_ref="d",
        )
        assert insight.claim_type.value == claim_type


def test_candidate_is_immutable() -> None:
    insight = CandidateInsight(
        insight_id="i", claim="c", claim_type=ClaimType.TREND, variables=["a"], dataset_ref="d"
    )
    with pytest.raises(ValidationError):
        insight.insight_id = "tampered"  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"insight_id": ""},
        {"claim": ""},
        {"variables": []},
        {"variables": ["a", "a"]},
        {"variables": ["a", "  "]},
        {"dataset_ref": ""},
        {"claim_type": "causation"},
        {"unexpected_field": 1},
    ],
)
def test_malformed_candidates_are_refused(overrides: dict[str, object]) -> None:
    fields: dict[str, object] = {
        "insight_id": "i",
        "claim": "c",
        "claim_type": ClaimType.CORRELATION,
        "variables": ["a", "b"],
        "dataset_ref": "d",
    }
    fields.update(overrides)
    with pytest.raises(ValidationError):
        CandidateInsight(**fields)  # type: ignore[arg-type]


# --- ProofObject: the prime-directive invariant ---------------------------


def test_supported_proof_is_valid() -> None:
    proof = _proof()
    assert proof.verdict is Verdict.PASS
    assert proof.evidence_score is not None


@pytest.mark.parametrize(
    "outcome",
    [GateOutcome.REFUTED, GateOutcome.NEGLIGIBLE, GateOutcome.INCONCLUSIVE],
)
def test_non_supported_outcomes_must_reject(outcome: GateOutcome) -> None:
    """A PASS verdict on anything but SUPPORTED is unconstructable (AGENTS.md 0)."""
    with pytest.raises(ValidationError, match="contradicts gate_outcome"):
        _proof(verdict=Verdict.PASS, gate_outcome=outcome, evidence_score=None)


def test_supported_outcome_cannot_carry_a_reject_verdict() -> None:
    with pytest.raises(ValidationError, match="contradicts gate_outcome"):
        _proof(verdict=Verdict.REJECT, gate_outcome=GateOutcome.SUPPORTED)


def test_supported_proof_requires_a_score() -> None:
    with pytest.raises(ValidationError, match="must carry an evidence_score"):
        _proof(evidence_score=None)


@pytest.mark.parametrize(
    "outcome",
    [GateOutcome.REFUTED, GateOutcome.NEGLIGIBLE, GateOutcome.INCONCLUSIVE],
)
def test_rejected_proof_must_not_carry_a_score(outcome: GateOutcome) -> None:
    """Scoring a non-finding invites someone ranking it as a finding."""
    with pytest.raises(ValidationError, match="must be null"):
        _proof(verdict=Verdict.REJECT, gate_outcome=outcome, evidence_score=0.4)


def test_failed_test_still_produces_a_complete_proof_object() -> None:
    """Fail-closed: a crashed test yields a full REJECT record, never a partial one
    and never a PASS (AGENTS.md 3.1, 3.6)."""
    proof = _proof(
        verdict=Verdict.REJECT,
        gate_outcome=GateOutcome.INCONCLUSIVE,
        evidence_score=None,
        p_value=1.0,
        q_value=1.0,
        effect_size=0.0,
        falsification_code="",
        failure_reason="executor timeout after 60s",
    )
    assert proof.verdict is Verdict.REJECT
    assert proof.failure_reason is not None
    assert set(ProofObject.model_fields) <= set(proof.model_dump())


def test_proof_round_trips() -> None:
    original = _proof(
        score_components=ScoreComponents(s_q=0.7, s_e=0.5, s_r=1.0),
        reported_effect=0.44,
        reported_effect_metric="pearson_r",
        asserted_direction=Direction.POSITIVE,
        observed_direction=Direction.POSITIVE,
        outlier_warning=False,
    )
    assert ProofObject.model_validate_json(original.model_dump_json()) == original


def test_proof_is_immutable() -> None:
    with pytest.raises(ValidationError):
        _proof().verdict = Verdict.REJECT  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"p_value": 1.5},
        {"q_value": -0.1},
        {"evidence_score": 1.2},
        {"n_hypotheses_in_batch": 0},
        {"bh_family_id": ""},
        {"insight_id": ""},
        {"extra_field": "x"},
    ],
)
def test_malformed_proofs_are_refused(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _proof(**overrides)


def test_bh_family_id_is_mandatory() -> None:
    """Reviewers will ask what the BH family was; the proof object must answer it."""
    fields = {
        "insight_id": "i",
        "verdict": Verdict.REJECT,
        "p_value": 0.5,
        "q_value": 0.9,
        "effect_size": 0.0,
        "test_type": TestType.PERMUTATION,
        "falsification_code": "",
        "n_hypotheses_in_batch": 3,
        "gate_outcome": GateOutcome.INCONCLUSIVE,
        "effect_metric": EffectMetric.SPEARMAN_RHO,
        "seed": 1,
    }
    with pytest.raises(ValidationError):
        ProofObject(**fields)  # type: ignore[arg-type]
