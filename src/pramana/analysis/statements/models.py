"""Structured statements: what a sentence like "revenue fell 12% in Q3" claims, in a form code can check.

The menu is closed. A model may fill these fields from a sentence; it never supplies the
result. Code recomputes every figure from the table and writes the verdict wording.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.computed.models import Scalar

Granularity = Literal["month", "quarter", "year"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChangeStatement(_Frozen):
    """A measure moved between two periods, e.g. "revenue fell 12% in Q3"."""

    kind: Literal["change"]
    measure: str = Field(max_length=256)
    granularity: Granularity
    to_period: str = Field(max_length=40, description='e.g. "2023Q3", "2023-09" or "2023"')
    baseline: Literal["previous", "year_ago"] = "previous"
    from_period: str | None = Field(default=None, max_length=40)
    stated_pct: float | None = Field(default=None, description="Signed: -12 for a 12% fall.")


class ShareStatement(_Frozen):
    """One group's share of a measure, e.g. "North is 60% of revenue"."""

    kind: Literal["share"]
    measure: str = Field(max_length=256)
    group_column: str = Field(max_length=256)
    group: str = Field(max_length=256)
    stated_pct: float | None = None


class RankStatement(_Frozen):
    """Which group is highest or lowest, e.g. "North is our biggest region"."""

    kind: Literal["rank"]
    measure: str = Field(max_length=256)
    group_column: str = Field(max_length=256)
    group: str = Field(max_length=256)
    position: Literal["highest", "lowest"]


class AssociationStatement(_Frozen):
    """Two columns go together, e.g. "price rises with carat". Tested by the gateway."""

    kind: Literal["association"]
    x: str = Field(max_length=256)
    y: str = Field(max_length=256)
    direction: Literal["positive", "negative"] | None = None


class CausalStatement(_Frozen):
    """One thing caused or should change another. A table alone cannot settle this."""

    kind: Literal["causal"]
    cause: str = Field(max_length=256)
    effect: str = Field(max_length=256)


class ForecastStatement(_Frozen):
    """A projection, e.g. "next quarter will be about 5 million"."""

    kind: Literal["forecast"]
    measure: str = Field(max_length=256)
    horizon: str = Field(default="", max_length=60)
    stated_value: float | None = None


Statement = Annotated[
    ChangeStatement
    | ShareStatement
    | RankStatement
    | AssociationStatement
    | CausalStatement
    | ForecastStatement,
    Field(discriminator="kind"),
]

Status = Literal[
    "matches",  # the table gives the stated figure
    "off_by",  # it gives a different figure
    "ambiguous",  # it matches only under another reading of the sentence
    "tested",  # the gateway tested it; see its verdict
    "not_tested",  # the gateway can test it but has not
    "not_testable",  # a table cannot settle it
    "cannot_check",  # the table lacks what the check needs
]


class Reading(_Frozen):
    """One way to read the sentence, and the figure the table gives for it."""

    label: str
    value: float | None = None
    matches: bool = False


class CheckResult(_Frozen):
    """What code found. `headline` is written by code from the numbers in `readings`."""

    kind: str
    status: Status
    headline: str
    detail: str = ""
    readings: list[Reading] = Field(default_factory=list)
    values: dict[str, Scalar] = Field(default_factory=dict)


class CheckedStatement(_Frozen):
    statement: dict[str, Scalar | list[str]]
    result: CheckResult
