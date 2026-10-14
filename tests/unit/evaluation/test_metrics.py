"""Precision, recall and empirical FDR on a hand-built truth table: exact, not approximate."""

from __future__ import annotations

import pytest

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType, Direction
from pramana.evaluation.config import RelationshipType, SignDirection
from pramana.evaluation.metrics import aggregate_scores, claim_matches, score_reported
from pramana.evaluation.planted import GroundTruth, TruthRow
from pramana.evaluation.report_tables import build_report_table


def _truth() -> GroundTruth:
    rows = [
        TruthRow(
            var_a="a", var_b="b", label="injected",
            relationship_type=RelationshipType.MONOTONIC,
            direction=SignDirection.POSITIVE, effect_level="clear",
        ),
        TruthRow(
            var_a="c", var_b="d", label="injected",
            relationship_type=RelationshipType.TREND,
            direction=SignDirection.NEGATIVE, effect_level="just_above",
        ),
        TruthRow(
            var_a="e", var_b="g", label="injected",
            relationship_type=RelationshipType.SHIFT,
            direction=SignDirection.POSITIVE, effect_level="clear",
            reference_group="1.0", levels=["1.0", "2.0"],
        ),
        TruthRow(var_a="a", var_b="c", label="null"),
        TruthRow(var_a="b", var_b="d", label="null"),
    ]
    return GroundTruth(
        dataset_id="hand", build_seed=1, base_seed=1, dataset_index=0, k=3,
        schedule=[], frame_digest="x", rows=rows,
    )


def _cand(
    insight_id: str, claim_type: ClaimType, variables: list[str],
    direction: Direction | None, reference_group: str | None = None,
) -> CandidateInsight:
    return CandidateInsight(
        insight_id=insight_id,
        claim=f"{variables[0]} is associated with {variables[1]}",
        claim_type=claim_type,
        variables=variables,
        dataset_ref="hand",
        asserted_direction=direction,
        reference_group=reference_group,
    )


TP_CORR = _cand("tp-corr", ClaimType.CORRELATION, ["b", "a"], Direction.POSITIVE)
TP_SHIFT = _cand("tp-shift", ClaimType.GROUP_DIFFERENCE, ["e", "g"], Direction.POSITIVE, "1.0")
WRONG_DIRECTION = _cand("wrong", ClaimType.TREND, ["c", "d"], Direction.POSITIVE)
NULL_PAIR = _cand("null", ClaimType.CORRELATION, ["a", "c"], Direction.POSITIVE)


def test_exact_precision_recall_and_fdp() -> None:
    reported = [TP_CORR, TP_SHIFT, WRONG_DIRECTION, NULL_PAIR]
    score = score_reported(_truth(), reported)
    assert score.n_reported == 4
    assert score.n_true_positive == 2
    assert score.n_false_positive == 2
    assert score.precision == 2 / 4
    assert score.n_injected == 3
    assert score.n_recovered == 2
    assert score.recall == 2 / 3
    assert score.fdp == 2 / 4
    assert score.recovered_by_level == {"clear": 2, "just_above": 0}
    assert score.injected_by_level == {"clear": 2, "just_above": 1}


def test_wrong_direction_is_a_false_positive_not_partial_credit() -> None:
    score = score_reported(_truth(), [WRONG_DIRECTION])
    assert score.n_true_positive == 0
    assert score.n_false_positive == 1
    assert score.recall == 0.0


def test_correct_negative_direction_counts() -> None:
    right = _cand("right", ClaimType.TREND, ["d", "c"], Direction.NEGATIVE)
    assert score_reported(_truth(), [right]).n_true_positive == 1


def test_group_direction_is_relative_to_the_reference_group() -> None:
    # "2.0 is lower" is the same finding as "1.0 is higher".
    flipped = _cand("flip", ClaimType.GROUP_DIFFERENCE, ["e", "g"], Direction.NEGATIVE, "2.0")
    wrong = _cand("wrong", ClaimType.GROUP_DIFFERENCE, ["e", "g"], Direction.NEGATIVE, "1.0")
    truth = _truth()
    assert claim_matches(truth.rows[2], flipped)
    assert not claim_matches(truth.rows[2], wrong)


def test_conservative_rules_for_unspecified_cases() -> None:
    undirected = _cand("undirected", ClaimType.CORRELATION, ["a", "b"], None)
    wrong_type = _cand("wrongtype", ClaimType.GROUP_DIFFERENCE, ["a", "b"], Direction.POSITIVE)
    unknown_column = _cand("ghost", ClaimType.CORRELATION, ["a", "zzz"], Direction.POSITIVE)
    score = score_reported(_truth(), [undirected, wrong_type, unknown_column])
    assert score.n_true_positive == 0
    assert score.n_false_positive == 3


def test_duplicate_reports_count_once_for_recall_and_each_for_precision() -> None:
    twin = _cand("tp-corr-2", ClaimType.TREND, ["a", "b"], Direction.POSITIVE)
    score = score_reported(_truth(), [TP_CORR, twin])
    assert score.n_true_positive == 2
    assert score.n_recovered == 1
    assert score.recall == 1 / 3


def test_nothing_reported_has_undefined_precision_and_zero_fdp() -> None:
    score = score_reported(_truth(), [])
    assert score.precision is None
    assert score.fdp == 0.0
    assert score.recall == 0.0


def test_no_injections_has_undefined_recall() -> None:
    truth = _truth().model_copy(update={"rows": [r for r in _truth().rows if r.label == "null"]})
    score = score_reported(truth, [NULL_PAIR])
    assert score.recall is None
    assert score.n_true_positive == 0
    assert score.fdp == 1.0


def test_aggregate_pools_and_averages_fdp() -> None:
    first = score_reported(_truth(), [TP_CORR, NULL_PAIR])  # fdp 1/2
    second = score_reported(_truth(), [])  # fdp 0 by convention
    agg = aggregate_scores([first, second])
    assert agg.n_datasets == 2
    assert agg.precision == 1 / 2
    assert agg.recall == 1 / 6
    assert agg.mean_fdp == pytest.approx((0.5 + 0.0) / 2)
    assert agg.pooled_fdp == 1 / 2


def test_report_table_has_every_condition_row_and_n() -> None:
    first = score_reported(_truth(), [TP_CORR, NULL_PAIR])
    table = build_report_table({"A": [first], "D": [first]}, alpha=0.05)
    assert [r["condition"] for r in table.rows] == ["A", "D"]
    assert all(r["n_datasets"] == 1 for r in table.rows)
    markdown = table.to_markdown()
    assert "| A |" in markdown and "| D |" in markdown
    assert "directional" in markdown.lower()
    d_row = table.rows[1]
    assert d_row["empirical_fdr"] == 0.5 and d_row["nominal_alpha"] == 0.05
    assert table.rows[0]["empirical_fdr"] is None  # FDR is only reported for the gated condition
