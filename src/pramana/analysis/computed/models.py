"""Payloads of the Exact tier: each figure carries the work that produced it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.computed.charts import ChartSpec
from pramana.analysis.sectors import SectorMatch
from pramana.analysis.shape import ShapeProfile

Scalar = float | int | str | bool | None

#: Bumped whenever stored analyses should be rebuilt (new figures or chart data).
#: 2 = chart data on figures and the report summary; 3 = clearer change wording.
COMPUTED_VERSION = 3


class ExactItem(BaseModel):
    """One computed figure and how to check it by hand.

    Guarantees: `level` is always "exact" (arithmetic on the table, no uncertainty
    claimed); `sentence` is rendered by code from a template; an item with
    `status == "not_run"` carries a user-safe `reason` and no values.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: str
    level: Literal["exact"] = "exact"
    status: Literal["ok", "not_run"] = "ok"
    title: str
    sentence: str = ""
    reason: str | None = None
    formula: str = ""
    columns: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    n_rows: int = Field(default=0, ge=0)
    values: dict[str, Scalar] = Field(default_factory=dict)
    table: list[dict[str, Scalar]] = Field(default_factory=list)
    chart: ChartSpec | None = None


class SummaryLine(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    item_id: str
    text: str


class ReportSummary(BaseModel):
    """The summary shown first on the report, with where its wording came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    source: Literal["template", "model"]
    lines: list[SummaryLine]
    fallback_reason: str | None = None


class ComputedAnalysis(BaseModel):
    """Everything the Exact tier found for one table. Shown to the user only (D5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = Field(default=0, ge=0, description="COMPUTED_VERSION that built it.")
    sector: SectorMatch
    shape: ShapeProfile
    scope_note: str = ""
    items: list[ExactItem]
    summary: ReportSummary | None = None
