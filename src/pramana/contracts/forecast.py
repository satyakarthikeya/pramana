"""`ForecastSpec` and `ForecastEvidence`: what a forecast claim names and what its backtest showed.

A forecast claim is a claim about PAST OUT-OF-SAMPLE ACCURACY: a named method, fitted only on
earlier periods, beat a baseline on periods it did not see. It says nothing certain about the
next periods, and the contract carries the sentence that says so (`FORECAST_BACKTEST_NOTE`),
so the limit travels with every proof instead of living in one screen's text.

Both models are optional additions with defaults on their parents (`CandidateInsight.forecast`,
`ProofObject.forecast`), so every candidate and every stored proof written before this file
existed still loads unchanged.

Owner: P.P. Satya Karthikeya
Scope: docs/evidence/FORECAST_CLAIM_2026-10-25.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Shown beside every forecast claim that passed; the one place to change its wording.
FORECAST_BACKTEST_NOTE = (
    "This measures how accurate the method was on earlier periods. "
    "It does not guarantee the next periods."
)

ForecastMethod = Literal["trend_seasonal", "holt_winters"]
ForecastBaseline = Literal["seasonal_naive", "naive"]


#: How each method is named in a claim sentence. The same names the Measured tier shows.
METHOD_LABELS: dict[str, str] = {
    "trend_seasonal": "linear trend with seasonal dummies",
    "holt_winters": "Holt-Winters exponential smoothing",
}

_BASELINE_PHRASES: dict[str, str] = {
    "seasonal_naive": "a seasonal-naive forecast",
    "naive": "a last-value forecast",
}


def render_forecast_claim(column: str, spec: ForecastSpec) -> str:
    """The one sentence a forecast claim may have, written by code and never by a model.

    Guarantees: states an accuracy on periods the method did not see, over the stated horizon,
    and nothing about the next periods; contains none of the words the admissibility screen
    refuses for a forecast (proven, will be, guaranteed, true, correct).
    """
    return (
        f"A forecast of {column} by {METHOD_LABELS[spec.method]} beats "
        f"{_BASELINE_PHRASES[spec.baseline]}, measured on periods it did not see, "
        f"over {spec.horizon} periods ahead."
    )


class ForecastSpec(BaseModel):
    """What the planner may ask for and code then fixes: horizon, method, baseline, aggregation.

    Guarantees: frozen; every field is a closed menu or a bounded integer. The model that
    proposed the claim supplies only the column and the horizon; `method`, `baseline` and
    `aggregate` are chosen by code on EXPLORATION rows, before any held-back period is read.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    horizon: int = Field(ge=1, le=24, description="Periods ahead each backtest origin forecasts.")
    method: ForecastMethod
    baseline: ForecastBaseline = "seasonal_naive"
    aggregate: Literal["sum", "mean"] = Field(
        default="mean", description="How rows of one period become one value."
    )


class ForecastOrigin(BaseModel):
    """One scored backtest point: what happened, what the method said, what the baseline said."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: str = Field(
        description="Label of the period the forecast was made from (the last one seen)."
    )
    target: str = Field(description="Label of the period that was forecast.")
    horizon: int = Field(ge=1)
    actual: float
    forecast: float
    baseline: float


class ForecastEvidence(BaseModel):
    """The backtest behind one forecast claim, in the units a reader can check.

    Guarantees: frozen; every number was computed by trusted code from the held-back periods
    (`origins`) or from the whole backtest (`mase_*`, `horizon_reductions`); `disclaimer`
    always carries the limit of what a backtest says.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: ForecastMethod
    baseline: ForecastBaseline
    horizon: int = Field(ge=1)
    season: int = Field(ge=1, description="Periods per seasonal cycle the method modelled.")
    period: str = Field(description="What one period is: month or quarter.")
    n_origins: int = Field(ge=1)
    n_blocks: int = Field(ge=1, description="Blocks of origins swapped together by the null.")
    first_origin: str
    last_origin: str
    mase_model: float
    mase_baseline: float
    error_reduction: float = Field(
        description="1 - MASE ratio; positive means the method was closer."
    )
    horizon_reductions: list[float] = Field(default_factory=list)
    reduction_vs_last_value: float | None = Field(
        default=None,
        description="The same reduction against a last-value forecast, shown for context only.",
    )
    interval_level: float | None = None
    interval_coverage: float | None = None
    interval_calibrated: bool | None = None
    origins: list[ForecastOrigin] = Field(default_factory=list)
    disclaimer: str = FORECAST_BACKTEST_NOTE
