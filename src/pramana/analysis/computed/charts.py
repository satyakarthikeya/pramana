"""Chart data for Exact figures: series computed by code, drawn as-is by the UI.

A chart never adds a number the figure does not already rest on: the line is the
period totals the change was computed from, the waterfall's steps are the segment
changes, the Pareto bars are the concentration totals.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Chart(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LineChart(_Chart):
    kind: Literal["line"] = "line"
    x_label: str
    y_label: str
    points: list[tuple[str, float]]
    marks: list[str] = Field(default_factory=list, description="x labels to highlight.")


class Bar(_Chart):
    label: str
    value: float
    n: int | None = None


class BarChart(_Chart):
    kind: Literal["bar"] = "bar"
    x_label: str
    y_label: str
    value_format: Literal["number", "percent"] = "number"
    bars: list[Bar]


class WaterfallStep(_Chart):
    label: str
    value: float


class WaterfallChart(_Chart):
    kind: Literal["waterfall"] = "waterfall"
    y_label: str
    start_label: str
    end_label: str
    start: float
    end: float
    steps: list[WaterfallStep]


class ParetoBar(_Chart):
    label: str
    value: float
    cumulative_share: float


class ParetoChart(_Chart):
    kind: Literal["pareto"] = "pareto"
    y_label: str
    bars: list[ParetoBar]


class HeatCell(_Chart):
    label: str
    index: float


class HeatStrip(_Chart):
    kind: Literal["heat_strip"] = "heat_strip"
    label: str
    cells: list[HeatCell]


ChartSpec = Annotated[
    LineChart | BarChart | WaterfallChart | ParetoChart | HeatStrip,
    Field(discriminator="kind"),
]
