"""Payloads of the Measured tier: a model's score on data it did not see, against a baseline.

A Measured item is never a finding and never a claim: it says how well a method did on
rows it was not fitted on, and how that compares with doing nothing clever (D3). Nothing
here reaches the gateway, a model or memory.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.computed.charts import ChartSpec
from pramana.analysis.computed.models import Scalar

#: Bumped whenever stored analyses should be rebuilt.
MEASURED_VERSION = 1

Kind = Literal[
    "driver_regression",
    "driver_classification",
    "adjusted_association",
    "segments",
    "anomalies",
    "forecast",
    "threshold",
]
Status = Literal["ok", "not_run", "no_lift", "withheld"]


class Exclusion(BaseModel):
    """A column kept out of a model, with the plain reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    column: str
    reason: str


class MeasuredItem(BaseModel):
    """One measured result.

    Guarantees: `level` is always "measured"; `sentence` is rendered by code from a
    template using only numbers in `values`; a `not_run` item carries a user-safe
    `reason`; a `withheld` item shows no score as a result; `no_lift` is a result, not
    a failure (no model beat the baseline).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: Kind
    level: Literal["measured"] = "measured"
    status: Status = "ok"
    title: str
    sentence: str = ""
    reason: str | None = None
    target: str | None = None
    features: list[str] = Field(default_factory=list)
    model_family: str | None = None
    models_tried: int = Field(default=0, ge=0)
    split: str = ""
    baseline: str | None = None
    metric: str | None = None
    baseline_score: float | None = None
    model_score: float | None = None
    lift: float | None = None
    spread: float | None = Field(default=None, description="Fold-to-fold sd of the lift.")
    n_rows: int = Field(default=0, ge=0)
    values: dict[str, Scalar] = Field(default_factory=dict)
    table: list[dict[str, Scalar]] = Field(default_factory=list)
    chart: ChartSpec | None = None
    leakage: list[Exclusion] = Field(default_factory=list)


class MeasuredRequest(BaseModel):
    """A structured request for one Measured analysis (what the P4 planner will send).

    The task, columns and controls are chosen from the closed menu; nothing here is
    code. For `adjusted_association` the variable of interest is `features[0]` and
    `controls` are the columns held in the model. For `threshold` `features[0]` is
    the column searched for a breakpoint. `target` is optional for segments/anomalies.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: Kind
    target: str | None = None
    features: list[str] = Field(default_factory=list)
    controls: list[str] = Field(default_factory=list)


class MeasuredAnalysis(BaseModel):
    """Everything the Measured tier computed for one table. Shown to the user only (D5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = Field(default=0, ge=0, description="MEASURED_VERSION that built it.")
    seed: int
    n_rows: int = Field(ge=0, description="Rows in the table.")
    sampled_rows: int | None = Field(
        default=None, description="Rows used when the table was sampled (seed above)."
    )
    items: list[MeasuredItem]
    excluded: list[Exclusion] = Field(
        default_factory=list, description="Columns kept out of models, over all items."
    )
    #: Elapsed seconds, so a slow table is visible rather than silent.
    seconds: float = Field(default=0.0, ge=0)
