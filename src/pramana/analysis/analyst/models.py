"""Payloads of the analyst read: the agent's plain-language reading of the report's results.

The read never holds a number the code did not compute: every paragraph cites facts, and
a paragraph survives only if every number in it appears in a fact it cites. Nothing here is
a claim, a verdict or a memory write.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.computed.models import Scalar
from pramana.analysis.statements.models import CheckResult

#: Bumped when stored reads should be rebuilt.
ANALYST_VERSION = 2


class Fact(BaseModel):
    """One code-computed result the agent may cite, with the numbers it may quote."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    tier: Literal["exact", "measured", "described"]
    title: str
    sentence: str = ""
    values: dict[str, Scalar] = Field(default_factory=dict)
    table: list[dict[str, Scalar]] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)


class Paragraph(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_ids: list[str] = Field(min_length=1, max_length=6)
    text: str = Field(min_length=1, max_length=600)
    #: What code recomputed for the structured claims the agent attached to this paragraph.
    checks: list[CheckResult] = Field(default_factory=list)


class AgentRequest(BaseModel):
    """An analysis the agent asked for from the closed menu, and what code did with it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: str
    target: str | None = None
    features: list[str] = Field(default_factory=list)
    accepted: bool
    note: str = ""


class AgentStep(BaseModel):
    """One tool or Python run the agent made while reading the table, kept so it can be audited."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    tool: str
    summary: str = Field(max_length=800, description="The arguments; Python shows its code.")
    output: str = Field(default="", max_length=1200)
    ok: bool


class AnalystRead(BaseModel):
    """The agent's reading of one table, or the code's own sentences when it was not used."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = Field(default=ANALYST_VERSION, ge=0)
    source: Literal["model", "template"]
    paragraphs: list[Paragraph]
    facts: list[Fact] = Field(default_factory=list)
    requests: list[AgentRequest] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    paragraphs_dropped: int = Field(default=0, ge=0)
    fallback_reason: str | None = None
