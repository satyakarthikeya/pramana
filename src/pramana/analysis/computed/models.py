"""Payloads of the Exact tier: each figure carries the work that produced it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.sectors import SectorMatch
from pramana.analysis.shape import ShapeProfile

Scalar = float | int | str | bool | None


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


class ComputedAnalysis(BaseModel):
    """Everything the Exact tier found for one table. Shown to the user only (D5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sector: SectorMatch
    shape: ShapeProfile
    scope_note: str = ""
    items: list[ExactItem]
