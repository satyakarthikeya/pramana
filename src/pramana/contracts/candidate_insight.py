"""`CandidateInsight` -- the analysis agent's output, the gateway's input (PROJECT.md 5).

The model refuses malformed candidates at the boundary rather than letting them reach
the executor. A claim naming the same column twice, or naming none at all, has no
falsification test that means anything; catching it here turns a 60-second sandbox
crash into an immediate, readable error.

Two fields extend PROJECT.md 5, both additive and both defaulted, so a producer that
predates them stays valid:

  * `asserted_direction` -- "rises with" is a directed claim. Without it the gate
    could pass a claim whose effect points the other way (see `GateOutcome.REFUTED`).
  * `reference_group` -- which level of a group-difference claim the sentence is
    about, so a signed effect can be oriented to match the words.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 1
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pramana.contracts.enums import ClaimType, Direction


class CandidateInsight(BaseModel):
    """One unverified claim, on its way to the gate.

    Guarantees: frozen (a candidate cannot be edited after the analysis agent emitted
    it, so the claim that was tested is the claim that was proposed), unknown fields
    are refused rather than silently dropped, and `variables` is a non-empty list of
    distinct, non-blank column names.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    insight_id: str = Field(min_length=1, description="Unique within a run.")
    claim: str = Field(min_length=1, description="Natural-language statement of the insight.")
    claim_type: ClaimType
    variables: list[str] = Field(min_length=1, description="Columns the claim is about.")
    dataset_ref: str = Field(min_length=1, description="Path or handle to the cleaned frame.")
    analysis_evidence: dict[str, Any] = Field(
        default_factory=dict,
        description="What the analysis agent saw. Never trusted as proof of anything.",
    )
    asserted_direction: Direction | None = Field(
        default=None,
        description="Direction the claim asserts. Null for an undirected claim.",
    )
    reference_group: str | None = Field(
        default=None,
        description="For group_difference: the level the claim is about, put first so a "
        "positive effect means what the sentence says.",
    )

    @field_validator("insight_id", "claim", "dataset_ref", "reference_group")
    @classmethod
    def _reject_blank(cls, value: str | None) -> str | None:
        """A whitespace-only identifier is an empty one wearing a disguise."""
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("variables")
    @classmethod
    def _distinct_named_columns(cls, variables: list[str]) -> list[str]:
        """Guarantees: every entry is a real column name, and no name repeats.

        A repeated column would make the claim self-referential -- correlating a
        column with itself is a p-value of 0 that proves nothing.
        """
        blank = [name for name in variables if not name.strip()]
        if blank:
            raise ValueError("variables must not contain blank column names")
        if len(set(variables)) != len(variables):
            raise ValueError(f"variables must be distinct; got {variables}")
        return variables
