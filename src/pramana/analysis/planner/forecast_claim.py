"""Code-rendered candidates for the forecast claim the planner may ask for.

The model supplies two structured fields, a column and a horizon. Everything else is code:
the method and the baseline are chosen here on the EXPLORATION rows alone (a short rolling
backtest at the end of the exploration periods), the sentence is written by
`pramana.contracts.render_forecast_claim`, and the gateway then tests the claim on periods
held back from this function and from the model. The `analysis_evidence` carries only what
was measured on exploration rows, and never a p-value, a q-value or a verdict.

Behind `claims.forecast_enabled` in `configs/verification.yaml` (false by default) and only
when the vetted template generator is selected: a model-written test never covers a forecast.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from pramana.analysis.measured.prep import num
from pramana.analysis.planner.models import DropReason, PlannedForecastRequest
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile
from pramana.analysis.shape import DataShape, ShapeProfile, period_keys
from pramana.contracts import (
    CandidateInsight,
    ClaimType,
    Direction,
    ForecastSpec,
    render_forecast_claim,
)
from pramana.verification.stats.forecast import (
    BASELINES,
    FORECAST_METHODS,
    period_series,
    relative_reduction,
    run_backtest,
    with_baseline,
)

if TYPE_CHECKING:
    from pramana.verification.config import ForecastConfig, VerificationConfig

_FREQ = {"month": "M", "quarter": "Q"}

#: Used when the exploration rows are too short to choose between methods; recorded as such.
_DEFAULT_METHOD = "trend_seasonal"
_DEFAULT_BASELINE = "seasonal_naive"


def forecast_offer() -> VerificationConfig | None:
    """The verification config when forecast claims may be offered, else None.

    Guarantees: None unless `claims.forecast_enabled` is true AND the vetted template generator
    is selected, so the planner never asks for a claim the gateway would refuse by design.
    """
    from pramana.verification.config import load_config

    config = load_config()
    if config.claims.forecast_enabled and config.llm.generator == "template":
        return config
    return None


def _exploration_series(
    frame: pd.DataFrame, schema: SchemaProfile, shape: ShapeProfile, target: str, aggregate: str
) -> tuple[np.ndarray, str] | None:
    """One value per period over the exploration rows, in time order, and the period type."""
    assert shape.time_column is not None
    keys, period = period_keys(frame, shape.time_column, schema)
    if period not in _FREQ:
        return None
    data = pd.DataFrame({"k": keys, "v": num(frame[target])}).dropna()
    if data.empty:
        return None
    ordinals = np.array([pd.Period(str(k), freq=_FREQ[period]).ordinal for k in data["k"]])
    try:
        series = period_series(
            ordinals,
            data["v"].to_numpy(dtype=float),
            aggregate=aggregate,  # type: ignore[arg-type]
            test_start_period=float(ordinals.max()),
            max_gap_fraction=1.0,
        )
    except ValueError:
        return None
    return series.values, period


def _select(
    values: np.ndarray, season: int, horizon: int, settings: ForecastConfig
) -> tuple[str, str, float | None, str]:
    """The method and baseline, chosen on the last few origins of the exploration periods.

    Returns `(method, baseline, exploration_reduction, how)`; the reduction is None and `how`
    says so when the exploration rows were too short to choose.
    """
    min_train = max(settings.min_cycles * season, settings.min_train_floor)
    start = max(min_train, values.size - horizon + 1 - settings.selection_origins)
    if values.size - horizon + 1 - start < 3:
        return _DEFAULT_METHOD, _DEFAULT_BASELINE, None, "default: too few exploration periods"
    runs: dict[tuple[str, str], Any] = {}
    for method in FORECAST_METHODS:
        try:
            fitted = run_backtest(
                values,
                method=method,
                season=season,
                horizon=horizon,
                test_start=start,
                min_train=min_train,
                baseline="seasonal_naive",
            )
            runs[(method, "seasonal_naive")] = fitted
            runs[(method, "naive")] = with_baseline(fitted, values, "naive")
        except Exception:  # a method that cannot be fitted is simply not a candidate
            continue
    if not runs:
        return _DEFAULT_METHOD, _DEFAULT_BASELINE, None, "default: no method could be fitted"
    baselines = ["seasonal_naive"] if settings.baseline == "seasonal_naive" else list(BASELINES)
    errors = {}
    for baseline in baselines:
        any_run = next((r for (m, b), r in runs.items() if b == baseline), None)
        if any_run is not None:
            errors[baseline] = float(np.mean(np.abs(any_run.actual - any_run.baseline)))
    if not errors:
        return _DEFAULT_METHOD, _DEFAULT_BASELINE, None, "default: no baseline could be scored"
    chosen = min(errors, key=lambda b: errors[b])
    scored = {
        method: relative_reduction(run.model_loss, run.baseline_loss)
        for (method, baseline), run in runs.items()
        if baseline == chosen
    }
    if not scored:
        return _DEFAULT_METHOD, chosen, None, "default: no method could be fitted"
    best = max(FORECAST_METHODS, key=lambda m: scored.get(m, -np.inf))
    return best, chosen, float(scored[best]), "exploration backtest"


def render_forecast_candidate(
    request: PlannedForecastRequest,
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    config: VerificationConfig,
    *,
    additive: bool,
    dataset_ref: str,
) -> tuple[CandidateInsight | None, tuple[DropReason, str] | None]:
    """A forecast candidate, or the reason it cannot be built.

    Guarantees: the variables are `[time column, column]`; the sentence is the contract's
    template; method and baseline come from exploration rows only; a request whose method
    did not beat its baseline on those rows is dropped rather than spent on the BH family.
    """
    settings = config.forecast
    target = request.column
    time = shape.time_column
    if time is None or shape.shape is DataShape.CROSS_SECTION:
        return None, ("wrong_shape", "a forecast needs a date or period column")
    if target == time or target not in frame.columns:
        return None, ("unknown_column", f"{target} is not a usable column to forecast")
    if schema.role_of(target) is not ColumnRole.NUMERIC:
        return None, ("wrong_shape", f"{target} is not a numeric column")
    if shape.period not in settings.seasonal_length:
        return None, (
            "wrong_shape",
            f"forecast claims are tested on {' or '.join(sorted(settings.seasonal_length))} "
            f"data; this table's period is {shape.period}",
        )
    if request.horizon > settings.max_horizon:
        return None, (
            "invalid_fields",
            f"a horizon of {request.horizon} periods exceeds the limit of {settings.max_horizon}",
        )
    aggregate = "sum" if additive and shape.shape is not DataShape.TIME_SERIES else "mean"
    laid = _exploration_series(frame, schema, shape, target, aggregate)
    if laid is None:
        return None, ("not_renderable", f"{target} has no usable series over the exploration rows")
    values, period = laid
    season = settings.seasonal_length[period]
    method, baseline, reduction, how = _select(values, season, request.horizon, settings)
    if reduction is None:
        # Too few exploration periods to choose a baseline: the default (seasonal-naive) is a weak
        # bar on a series without a season, so the claim is not proposed rather than guessed at.
        return None, (
            "not_renderable",
            f"the exploration periods are too few to choose a method and a baseline for "
            f"{target} ({how}), so the claim was not spent on the test",
        )
    if reduction <= 0.0:
        return None, (
            "not_renderable",
            f"on the exploration periods no method beat the {baseline.replace('_', '-')} "
            f"baseline for {target}, so the claim was not spent on the test",
        )
    spec = ForecastSpec(
        horizon=request.horizon,
        method=method,
        baseline=baseline,
        aggregate=aggregate,  # type: ignore[arg-type]
    )
    identity = json.dumps(
        {"request": request.model_dump(mode="json"), "spec": spec.model_dump(mode="json")},
        sort_keys=True,
    )
    evidence: dict[str, Any] = {
        "source": "planner_structured_proposal",
        "selection": how,
        "period": period,
        "n_exploration_periods": int(values.size),
        "method": method,
        "baseline": baseline,
    }
    if reduction is not None:
        evidence["exploration_error_reduction"] = reduction
    return (
        CandidateInsight(
            insight_id="plan-fc-" + hashlib.sha256(identity.encode()).hexdigest()[:22],
            claim=render_forecast_claim(target, spec),
            claim_type=ClaimType.FORECAST,
            variables=[time, target],
            dataset_ref=dataset_ref,
            analysis_evidence=evidence,
            asserted_direction=Direction.POSITIVE,
            forecast=spec,
        ),
        None,
    )
