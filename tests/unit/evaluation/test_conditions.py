"""Conditions A and D as flags on one pipeline; B and C are explicit stubs."""

from __future__ import annotations

import pandas as pd
import pytest

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType, Direction, Verdict
from pramana.evaluation.conditions import (
    CONDITION_FLAGS,
    Condition,
    ConditionRunError,
    Proposer,
    ProposerSet,
    run_condition,
)
from pramana.evaluation.config import EvaluationConfig, RelationshipType
from pramana.evaluation.planted import PlantedDataset, build_planted_dataset
from pramana.verification.config import VerificationConfig
from pramana.verification.falsification.generator import GeneratorUnavailable


def _dataset(extract, eval_config, ver_config, *, index: int, k: int) -> PlantedDataset:
    frame, ordinal = extract
    return build_planted_dataset(
        frame, dataset_id=f"ds-{index}", dataset_index=index, config=eval_config,
        verification=ver_config, ordinal_columns=ordinal, k=k,
    )


def _claim(insight_id, claim_type, variables, direction, dataset_id, reference_group=None):
    return CandidateInsight(
        insight_id=insight_id,
        claim=f"{variables[0]} is associated with {variables[1]}",
        claim_type=claim_type,
        variables=variables,
        dataset_ref=dataset_id,
        asserted_direction=direction,
        reference_group=reference_group,
    )


def null_claims(dataset: PlantedDataset, n: int) -> list[CandidateInsight]:
    """`n` correlation claims over pairs the truth table labels null (numeric columns only)."""
    numeric = [c for c in dataset.frame.columns if c.startswith("num_")]
    nulls = {
        frozenset((r.var_a, r.var_b)) for r in dataset.truth.rows if r.label == "null"
    }
    out: list[CandidateInsight] = []
    for i, a in enumerate(numeric):
        for b in numeric[i + 1 :]:
            if frozenset((a, b)) in nulls and len(out) < n:
                out.append(
                    _claim(f"null-{len(out)}", ClaimType.CORRELATION, [a, b],
                           Direction.POSITIVE, dataset.truth.dataset_id)
                )
    return out


def true_claims(dataset: PlantedDataset) -> list[CandidateInsight]:
    """One correctly directed claim per injected relationship."""
    out: list[CandidateInsight] = []
    for r in dataset.truth.rows:
        if r.label != "injected":
            continue
        direction = Direction(r.direction.value)
        if r.relationship_type is RelationshipType.SHIFT:
            out.append(_claim(f"true-{len(out)}", ClaimType.GROUP_DIFFERENCE,
                              [r.group_column, r.value_column], direction,
                              dataset.truth.dataset_id, r.reference_group))
        else:
            claim_type = (
                ClaimType.TREND if r.relationship_type is RelationshipType.TREND
                else ClaimType.CORRELATION
            )
            out.append(_claim(f"true-{len(out)}", claim_type, [r.var_a, r.var_b], direction,
                              dataset.truth.dataset_id))
    return out


def proposers_for(claims: list[CandidateInsight], model: str) -> ProposerSet:
    proposer = Proposer(model=model, propose=lambda frame: list(claims))
    return ProposerSet(single_call=proposer, analysis_loop=proposer)


@pytest.fixture(scope="module")
def null_dataset(extract, eval_config, ver_config) -> PlantedDataset:
    return _dataset(extract, eval_config, ver_config, index=3, k=0)


@pytest.fixture(scope="module")
def planted_dataset(extract, eval_config, ver_config) -> PlantedDataset:
    return _dataset(extract, eval_config, ver_config, index=0, k=3)


def test_flags_are_settings_on_one_pipeline() -> None:
    assert CONDITION_FLAGS[Condition.A].analysis_loop is False
    assert CONDITION_FLAGS[Condition.A].gate == "none"
    assert CONDITION_FLAGS[Condition.D].analysis_loop is True
    assert CONDITION_FLAGS[Condition.D].gate == "execution"


@pytest.mark.parametrize("condition", [Condition.B, Condition.C])
def test_b_and_c_are_stubs_that_say_where_to_look(
    condition, null_dataset, eval_config, ver_config
) -> None:
    with pytest.raises(NotImplementedError) as raised:
        run_condition(
            condition, null_dataset.frame, dataset_id="x",
            proposers=proposers_for([], eval_config.conditions.analysis_model),
            verification=ver_config, evaluation=eval_config,
        )
    message = str(raised.value)
    assert "SPEC.md" in message and "OPEN_ISSUES" in message and "issue 3" in message


def test_condition_a_reports_everything_with_no_gate(
    null_dataset, eval_config, ver_config
) -> None:
    claims = null_claims(null_dataset, 3)
    result = run_condition(
        Condition.A, null_dataset.frame, dataset_id="ds-3",
        proposers=proposers_for(claims, eval_config.conditions.analysis_model),
        verification=ver_config, evaluation=eval_config,
    )
    assert result.reported_ids == [c.insight_id for c in claims]
    assert result.proofs is None and result.bh_family_id is None and result.generator is None


def test_a_wrong_model_fails_closed(null_dataset, eval_config, ver_config) -> None:
    with pytest.raises(ConditionRunError, match="model"):
        run_condition(
            Condition.A, null_dataset.frame, dataset_id="ds-3",
            proposers=proposers_for(null_claims(null_dataset, 2), "some-other-model"),
            verification=ver_config, evaluation=eval_config,
        )


def test_a_failing_proposer_fails_closed_not_empty(
    null_dataset, eval_config, ver_config
) -> None:
    def boom(frame: pd.DataFrame) -> list[CandidateInsight]:
        raise RuntimeError("provider down")

    broken = Proposer(model=eval_config.conditions.analysis_model, propose=boom)
    with pytest.raises(ConditionRunError, match="provider down"):
        run_condition(
            Condition.A, null_dataset.frame, dataset_id="ds-3",
            proposers=ProposerSet(single_call=broken, analysis_loop=broken),
            verification=ver_config, evaluation=eval_config,
        )


@pytest.fixture(scope="module")
def d_null_result(null_dataset, eval_config: EvaluationConfig, ver_config: VerificationConfig):
    claims = null_claims(null_dataset, 5)
    assert len(claims) == 5
    return run_condition(
        Condition.D, null_dataset.frame, dataset_id="ds-3",
        proposers=proposers_for(claims, eval_config.conditions.analysis_model),
        verification=ver_config, evaluation=eval_config,
    )


def test_d_on_shuffled_only_data_passes_nothing(d_null_result) -> None:
    """k=0: any PASS is a false positive. TP is zero by construction; so must PASS be."""
    assert d_null_result.proofs is not None
    assert all(p.verdict is Verdict.REJECT for p in d_null_result.proofs)
    assert d_null_result.reported_ids == []
    assert d_null_result.bh_family_id is not None
    assert d_null_result.generator == "template"


def test_d_is_deterministic_given_the_seed(
    null_dataset, eval_config, ver_config, d_null_result
) -> None:
    again = run_condition(
        Condition.D, null_dataset.frame, dataset_id="ds-3",
        proposers=proposers_for(
            null_claims(null_dataset, 5), eval_config.conditions.analysis_model
        ),
        verification=ver_config, evaluation=eval_config,
    )
    first = [p.model_dump(exclude={"falsification_code"}) for p in d_null_result.proofs]
    second = [p.model_dump(exclude={"falsification_code"}) for p in again.proofs]
    assert first == second
    assert again.bh_family_id == d_null_result.bh_family_id


def test_d_passes_a_clear_planted_correlation_and_not_the_nulls(
    planted_dataset, eval_config, ver_config
) -> None:
    row = next(
        r for r in planted_dataset.truth.rows
        if r.label == "injected" and r.effect_level == "clear"
    )
    assert row.relationship_type is RelationshipType.MONOTONIC
    first = next(
        c for c in true_claims(planted_dataset) if set(c.variables) == {row.var_a, row.var_b}
    )
    claims = [first] + null_claims(planted_dataset, 2)
    result = run_condition(
        Condition.D, planted_dataset.frame, dataset_id="ds-0",
        proposers=proposers_for(claims, eval_config.conditions.analysis_model),
        verification=ver_config, evaluation=eval_config,
    )
    assert result.reported_ids == [first.insight_id]


def test_unreachable_generator_is_an_error_not_zero_insights(
    null_dataset, eval_config, ver_config
) -> None:
    def unreachable(candidate, config):
        raise GeneratorUnavailable("no key")

    with pytest.raises(ConditionRunError, match="generator"):
        run_condition(
            Condition.D, null_dataset.frame, dataset_id="ds-3",
            proposers=proposers_for(null_claims(null_dataset, 2),
                                    eval_config.conditions.analysis_model),
            verification=ver_config, evaluation=eval_config, generate=unreachable,
        )
