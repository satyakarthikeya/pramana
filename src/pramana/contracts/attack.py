"""`AttackResult` -- one attempt to break a finding that passed the gate (PLAN §7).

Attacks are a one-way ratchet: a `BROKEN` result turns a PASS into REJECT / FRAGILE,
and nothing here can turn a REJECT into a PASS. An attack that could not run is
`NOT_RUN` with its reason, and is never shown as survived.

Owner: P.P. Satya Karthikeya
Scope: PLAN_analysis_platform.md P5
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

AttackValue = float | int | str | bool | None


class AttackOutcome(StrEnum):
    """What one attack found."""

    SURVIVED = "survived"
    BROKEN = "broken"
    NOT_RUN = "not_run"


class AttackResult(BaseModel):
    """One attack on one finding, with the numbers it compared.

    Guarantees: `reason` is plain text written for the user; a `NOT_RUN` result carries
    no attacked effect; `attack_id` is one of A1..A7 from the plan's menu, or F1..F6 for a
    forecast claim.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    attack_id: str = Field(pattern=r"^(A[1-7]|F[1-6])$")
    name: str = Field(min_length=1)
    outcome: AttackOutcome
    reason: str = Field(min_length=1)
    original_effect: float | None = None
    attacked_effect: float | None = None
    n_rows: int | None = Field(default=None, ge=0)
    applicable: bool = Field(
        default=True,
        description="False when the attack's question does not exist for this claim or table "
        "(no grouping column, an unsigned effect, a claim type with no attack). A NOT_RUN "
        "result that is applicable could not be run on this data; neither counts as survived.",
    )
    details: dict[str, AttackValue] = Field(default_factory=dict)
