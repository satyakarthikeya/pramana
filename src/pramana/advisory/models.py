"""Payloads for the Skeptic and the Explainer. Pure data: nothing here can alter a verdict."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FollowUp(Payload):
    """A question worth testing in a NEXT run. It is never tested automatically."""

    sentence: str
    claim_type: Literal["correlation", "group_difference"]
    variables: list[str] = Field(min_length=2, max_length=2)


class Caveat(Payload):
    """One column that may account for part of a finding, with the numbers behind it."""

    insight_id: str
    control: str
    control_kind: Literal["numeric", "categorical"]
    measure: Literal["spearman_rho", "rank_eta_squared"]
    #: How strongly the control goes with each claim column (rank association, 0 to 1).
    link_first: float
    link_second: float
    #: The claim's own association on the rows where all three columns are recorded.
    before: float
    #: The same association when rows are compared at a similar value of the control.
    after: float
    n: int = Field(ge=1)
    text: str
    follow_ups: list[FollowUp] = Field(default_factory=list, max_length=3)


class FindingReview(Payload):
    insight_id: str
    status: Literal["flagged", "none_found", "not_checked"]
    #: Why nothing was checked, when status is not_checked.
    reason: str | None = None
    controls_checked: int = Field(default=0, ge=0)
    skipped_near_duplicates: int = Field(default=0, ge=0)
    caveats: list[Caveat] = Field(default_factory=list)


class Explanation(Payload):
    insight_id: str
    text: str
    #: Who wrote the sentence. A model sentence is only kept if code checked every number in it.
    source: Literal["template", "model"]
    #: Why the code-written sentence is shown when a model was configured.
    fallback_reason: str | None = None


class AdvisoryReport(Payload):
    explanations: list[Explanation] = Field(default_factory=list)
    reviews: list[FindingReview] = Field(default_factory=list)
    #: Plain statements about the advisory step itself (what was and was not run).
    notes: list[str] = Field(default_factory=list)
