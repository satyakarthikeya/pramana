"""Code-rendered candidates for the two time claims the planner may propose.

`period_change` and `seasonality` are not in the older proposers' `StructuredClaim`, so their
sentences are rendered here, from fixed hedged templates, never from model text. The
`analysis_evidence` carries only descriptive numbers computed from the EXPLORATION rows (a
difference of period means, an eta-squared over months); it never carries a p-value, a
q-value or a verdict, and the gateway recomputes everything on the confirmation rows.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import pandas as pd

from pramana.analysis.config import HypothesesConfig
from pramana.analysis.hypotheses.base import ClaimScreen
from pramana.analysis.hypotheses.group_difference import _eta_squared
from pramana.analysis.planner.models import PlannerClaim
from pramana.analysis.schema_inference import SchemaProfile
from pramana.analysis.shape import ShapeProfile, period_keys
from pramana.contracts import CandidateInsight, ClaimType, Direction

_UNIT = {"month": "month", "quarter": "quarter"}


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def change_sentence(y: str, direction: Direction | None) -> str:
    """The hedged sentence for a period-change claim."""
    if direction is Direction.POSITIVE:
        return f"{y} in the latest period tends to be higher than in the period before"
    if direction is Direction.NEGATIVE:
        return f"{y} in the latest period tends to be lower than in the period before"
    return f"{y} in the latest period tends to differ from the period before"


def seasonality_sentence(y: str, period: str) -> str:
    """The hedged sentence for a seasonality claim."""
    return f"{y} tends to differ by {_UNIT[period]} of the year"


def render_time_candidate(
    proposal: PlannerClaim,
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    config: HypothesesConfig,
    *,
    dataset_ref: str,
    claim_screen: ClaimScreen | None = None,
) -> CandidateInsight | None:
    """A candidate for a period-change or seasonality claim, or None if it cannot be built.

    Guarantees: the text comes from a template; the variables are exactly
    `[time column, measure]`; the evidence is descriptive and exploration-only. Shape and
    column checks are the planner's; this returns None when the rows cannot support the
    descriptive numbers (too few observations or periods).
    """
    x, y = proposal.variables
    kind = ClaimType(proposal.claim_type)
    if shape.time_column != x or x not in frame.columns or y not in frame.columns:
        return None
    keys, period = period_keys(frame, x, schema)
    data = pd.DataFrame({"k": keys, "v": pd.to_numeric(frame[y], errors="coerce")}).dropna()
    if len(data) < config.min_observations:
        return None
    direction = Direction(proposal.direction) if proposal.direction else None
    evidence: dict[str, Any] = {
        "source": "planner_structured_proposal",
        "n_observations": int(len(data)),
        "period": period,
    }
    if kind is ClaimType.PERIOD_CHANGE:
        if proposal.reference_group is not None:
            return None
        means = data.groupby("k")["v"].mean().sort_index()
        if len(means) < 2:
            return None
        change = _finite(means.iloc[-1] - means.iloc[-2])
        if change is None:
            return None
        evidence.update(stat="latest_minus_previous_period_mean", raw_value=change)
        text = change_sentence(y, direction)
    else:
        if direction is not None or proposal.reference_group is not None or period not in _UNIT:
            return None
        text_keys = data["k"].astype(str)
        position = text_keys.str[5:7] if period == "month" else text_keys.str[-1]
        groups = [g["v"] for _, g in data.groupby(position) if len(g) >= 2]
        if len(groups) < 2:
            return None
        eta = _finite(_eta_squared(groups))
        if eta is None:
            return None
        evidence.update(stat="eta_squared_by_position_in_year", raw_value=eta)
        text = seasonality_sentence(y, period)
    if claim_screen is not None and not claim_screen(text, kind, [x, y]):
        return None
    identity = json.dumps(proposal.model_dump(mode="json"), sort_keys=True, ensure_ascii=True)
    return CandidateInsight(
        insight_id="plan-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
        claim=text,
        claim_type=kind,
        variables=[x, y],
        dataset_ref=dataset_ref,
        analysis_evidence=evidence,
        asserted_direction=direction,
        reference_group=None,
    )
