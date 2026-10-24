"""A table above the trend-test row ceiling is still analysed; only trend claims are left out."""

from __future__ import annotations

from pramana.analysis.planner.models import AcceptedClaim, PlanRecord, ShapeConfirmation
from pramana.analysis.workspace.ledger import ExplorationSummary
from pramana.orchestration.analysis_integration import drop_oversize_trends
from pramana.verification.stats.effect_size import MAX_SENS_SLOPE_OBSERVATIONS
from tests.fixtures.candidates import candidate

TREND = candidate("t1", "revenue trends up over month", "trend", ["month", "revenue"])
OTHER = candidate("c1", "revenue and cost move together", "correlation", ["revenue", "cost"])


def _summary(plan: PlanRecord | None = None) -> ExplorationSummary:
    return ExplorationSummary(engine="planner", examined=2, proposed=2, plan=plan)


def test_a_small_table_keeps_every_claim() -> None:
    kept, summary = drop_oversize_trends([TREND, OTHER], _summary(), MAX_SENS_SLOPE_OBSERVATIONS)
    assert [c.insight_id for c in kept] == ["t1", "c1"] and summary.proposed == 2


def test_a_big_table_loses_only_its_trend_claims_and_says_why() -> None:
    plan = PlanRecord(
        model="m",
        shape="transactions",
        shape_confirmation=ShapeConfirmation(verdict="confirm"),
        accepted_claims=[
            AcceptedClaim(claim_type="trend", variables=["month", "revenue"], insight_id="t1"),
            AcceptedClaim(claim_type="correlation", variables=["revenue", "cost"], insight_id="c1"),
        ],
    )
    kept, summary = drop_oversize_trends(
        [TREND, OTHER], _summary(plan), MAX_SENS_SLOPE_OBSERVATIONS + 1
    )
    assert [c.insight_id for c in kept] == ["c1"]
    assert summary.proposed == 1
    assert [a.insight_id for a in summary.plan.accepted_claims] == ["c1"]
    drop = summary.plan.dropped[0]
    assert drop.what == "claim" and drop.item.startswith("trend(")
    assert "3,000" in drop.reason and "25" not in drop.reason  # names the ceiling, not a guess


def test_a_big_table_without_a_trend_claim_is_untouched() -> None:
    kept, summary = drop_oversize_trends([OTHER], _summary(), 25_000)
    assert kept == [OTHER] and summary.proposed == 2
