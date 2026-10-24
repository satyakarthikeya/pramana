"""The planner's structured output and the record of what code did with it (PLAN §6).

`AnalysisSpec` is everything the model may say: it can confirm or flag the table's shape
(never change it), ask for closed-menu Measured analyses, name structured claims, and
choose which already-computed items lead the summary. There is no free-text claim field
and no place for a number, a verdict or code: every model is `extra="forbid"`, so a reply
that tries is refused whole. Code renders claim sentences from templates.

This module must stay light: `workspace.ledger` imports it, so it imports nothing from
the workspace or the tiers' runners.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: The Measured tasks a plan may request (the Measured tier's closed menu).
MeasuredTask = Literal[
    "driver_regression",
    "driver_classification",
    "adjusted_association",
    "segments",
    "anomalies",
    "components",
    "forecast",
    "threshold",
]

#: Why the model wants a Measured analysis: a closed list, so no prose rides along.
ReasonCode = Literal[
    "strong_signal",
    "suspected_driver",
    "time_structure",
    "unusual_rows",
    "subgroup_structure",
    "adjust_for_control",
    "check_threshold",
    "other",
]

PlannerClaimType = Literal[
    "correlation", "group_difference", "trend", "period_change", "seasonality"
]

#: Why code dropped part of a plan.
DropReason = Literal[
    "unknown_column",
    "leakage",
    "over_budget",
    "duplicate",
    "wrong_shape",
    "not_renderable",
    "unknown_item",
    "invalid_fields",
    "bookkeeping",
    "time_label",
]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ShapeConfirmation(_Frozen):
    """The model may confirm or flag the shape. Code never changes the shape from it."""

    verdict: Literal["confirm", "flag"]
    note: str = Field(default="", max_length=200)

    @field_validator("note")
    @classmethod
    def _one_line(cls, value: str) -> str:
        """The note is the model's own words, shown as such: one plain line, no control text."""
        return " ".join(value.split())


class PlannedMeasuredRequest(_Frozen):
    """One requested Measured analysis, from the closed menu. Nothing here is code."""

    task: MeasuredTask
    target: str | None = Field(default=None, max_length=256)
    features: list[str] = Field(default_factory=list, max_length=30)
    controls: list[str] = Field(default_factory=list, max_length=30)
    reason_code: ReasonCode = "other"


class PlannerClaim(_Frozen):
    """A structured claim. No claim text, number, p-value, code or verdict is accepted."""

    claim_type: PlannerClaimType
    variables: list[str] = Field(min_length=2, max_length=2)
    direction: Literal["positive", "negative"] | None = None
    reference_group: str | None = Field(default=None, max_length=256)


class AnalysisSpec(_Frozen):
    """The whole of what DeepSeek returns as the plan."""

    shape_confirmation: ShapeConfirmation
    measured_requests: list[PlannedMeasuredRequest] = Field(default_factory=list, max_length=20)
    claims: list[PlannerClaim] = Field(default_factory=list, max_length=50)
    narrative_focus: list[str] = Field(default_factory=list, max_length=20)


class PlanDrop(_Frozen):
    """Something the model asked for that code did not accept, and why."""

    what: Literal["claim", "measured_request", "narrative_focus"]
    item: str = Field(max_length=300)
    reason_code: DropReason
    reason: str = Field(max_length=400)


class AcceptedClaim(_Frozen):
    claim_type: PlannerClaimType
    variables: list[str]
    insight_id: str


class PlanRecord(_Frozen):
    """What the planner did: accepted, dropped (with reasons) and what the call cost."""

    model: str
    shape: str
    shape_confirmation: ShapeConfirmation
    accepted_claims: list[AcceptedClaim] = Field(default_factory=list)
    accepted_measured: list[PlannedMeasuredRequest] = Field(default_factory=list)
    accepted_focus: list[str] = Field(default_factory=list)
    dropped: list[PlanDrop] = Field(default_factory=list)
    turns: int = Field(default=0, ge=0)
    repaired: bool = False
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
