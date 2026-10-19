"""Selection keeps strategy diversity without assigning verification outcomes."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from pramana.analysis.config import HypothesesConfig, StrategyMinimums, load_config
from pramana.analysis.prioritization import prioritize_candidates
from pramana.contracts import CandidateInsight
from pramana.contracts.enums import ClaimType


def candidate(name: str, kind: ClaimType, value: Any) -> CandidateInsight:
    return CandidateInsight(
        insight_id=name,
        claim="y is associated with x",
        claim_type=kind,
        variables=["x", "y"],
        dataset_ref="cleaned-frame",
        analysis_evidence={"stat": "exploratory_effect", "raw_value": value},
    )


def config(limit: int) -> HypothesesConfig:
    return load_config().hypotheses.model_copy(update={"max_candidates_per_run": limit})


def mixed() -> list[CandidateInsight]:
    return [
        candidate("c1", ClaimType.CORRELATION, 0.9),
        candidate("c2", ClaimType.CORRELATION, -0.8),
        candidate("c3", ClaimType.CORRELATION, 0.7),
        candidate("g1", ClaimType.GROUP_DIFFERENCE, 0.2),
        candidate("t1", ClaimType.TREND, 0.1),
    ]


def test_reservations_keep_weaker_strategies_from_being_crowded_out() -> None:
    selected = prioritize_candidates(mixed(), config=config(3))
    assert [item.insight_id for item in selected] == ["c1", "g1", "t1"]


def test_remaining_slots_follow_magnitude_and_input_order_does_not_matter() -> None:
    items = mixed()
    selected = prioritize_candidates(items, config=config(4))
    assert [item.insight_id for item in selected] == ["c1", "c2", "g1", "t1"]
    assert selected == prioritize_candidates(reversed(items), config=config(4))
    assert all(any(item is original for original in items) for item in selected)


def test_unused_reservations_do_not_waste_capacity() -> None:
    selected = prioritize_candidates(mixed()[:3], config=config(3))
    assert [item.insight_id for item in selected] == ["c1", "c2", "c3"]


def test_tiny_cap_uses_strongest_strategy_heads() -> None:
    selected = prioritize_candidates(mixed(), config=config(2))
    assert [item.insight_id for item in selected] == ["c1", "g1"]


def test_reservations_are_filled_in_rounds_when_they_exceed_the_cap() -> None:
    settings = config(3).model_copy(
        update={
            "strategy_min_candidates": StrategyMinimums(correlation=3, group_difference=2, trend=2)
        }
    )
    assert {item.insight_id for item in prioritize_candidates(mixed(), config=settings)} == {
        "c1",
        "g1",
        "t1",
    }


def test_zero_reservations_restore_magnitude_only_selection() -> None:
    settings = config(3).model_copy(
        update={
            "strategy_min_candidates": StrategyMinimums(correlation=0, group_difference=0, trend=0)
        }
    )
    assert [item.insight_id for item in prioritize_candidates(mixed(), config=settings)] == [
        "c1",
        "c2",
        "c3",
    ]


def test_disabled_strategy_cannot_consume_reserved_or_shared_slots() -> None:
    settings = config(3)
    settings = settings.model_copy(
        update={"strategies": settings.strategies.model_copy(update={"correlation": False})}
    )
    assert [item.insight_id for item in prioritize_candidates(mixed(), config=settings)] == [
        "g1",
        "t1",
    ]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), None, True, "9"])
def test_unusable_evidence_cannot_beat_a_finite_effect(bad: Any) -> None:
    items = [
        candidate("bad", ClaimType.CORRELATION, bad),
        candidate("good", ClaimType.CORRELATION, 0.01),
    ]
    assert prioritize_candidates(items, config=config(1))[0].insight_id == "good"


def test_ties_break_by_id_and_repeated_candidates_use_one_slot() -> None:
    a = candidate("a", ClaimType.CORRELATION, 0.5)
    b = candidate("b", ClaimType.CORRELATION, -0.5)
    assert prioritize_candidates([b, a, a], config=config(3)) == [a, b]
    with pytest.raises(ValueError, match="conflicting candidates"):
        prioritize_candidates(
            [a, a.model_copy(update={"claim": "a different claim"})], config=config(3)
        )


def test_empty_input_returns_an_empty_batch() -> None:
    assert prioritize_candidates([], config=config(3)) == []


@pytest.mark.parametrize("bad", [-1, 1.5, True, "2"])
def test_quota_requires_a_nonnegative_integer(bad: Any) -> None:
    with pytest.raises(ValidationError):
        StrategyMinimums(correlation=bad, group_difference=1, trend=1)
