"""Trusted-side helpers for forecast claims: rerun the backtest, attack it, describe it.

The sandboxed template computes the p-value and the effect. Everything else a forecast claim
shows is recomputed HERE, in the gateway process, from the same rows and the same stats
library (`pramana.verification.stats.forecast`): the attacks, the interval, the power note and
the table behind the claim card. Recomputing costs one more backtest per claim that passed,
and means no number on a card came from the sandbox's say-so.

Nothing in this module decides a verdict. `forecast_attacks` returns results the gateway
applies as a one-way ratchet, exactly like the attacks on other claims.

Owner: P.P. Satya Karthikeya
Scope: docs/evidence/FORECAST_CLAIM_2026-10-25.md
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from pramana.contracts import (
    AttackResult,
    EffectInterval,
    EffectMetric,
    ForecastEvidence,
    ForecastOrigin,
    PowerNote,
)
from pramana.verification.attacks.forecast import run_forecast_attacks, stated_interval
from pramana.verification.config import VerificationConfig
from pramana.verification.schemes import PERIOD_COLUMN, ForecastPlan
from pramana.verification.stats.forecast import (
    Backtest,
    PeriodSeries,
    detectable_reduction,
    origin_block_interval,
    period_series,
    relative_reduction,
    run_backtest,
    with_baseline,
)

_PERIOD_FREQ = {"month": "M", "quarter": "Q"}

#: Origins shown on the claim card at most, newest last: the card is a small table, not a ledger.
MAX_CARD_ORIGINS = 24


def forecast_frame(history: pd.DataFrame | None, held_back: pd.DataFrame) -> pd.DataFrame:
    """The rows the forecast test reads: the earlier rows (to fit on) and the held-back rows.

    The held-back window is carried in the plan (`test_start_period`), not in the frame, so a
    program that reads every row still cannot score an earlier period.
    """
    if history is None or history.empty:
        return held_back
    return pd.concat([history, held_back], ignore_index=True)


def _series_inputs(frame: pd.DataFrame, target: str) -> tuple[np.ndarray, np.ndarray]:
    rows = pd.DataFrame(
        {"p": frame[PERIOD_COLUMN], "v": pd.to_numeric(frame[target], errors="coerce")}
    ).dropna()
    return rows["p"].to_numpy(dtype=float), rows["v"].to_numpy(dtype=float)


def rerun(
    plan: ForecastPlan, frame: pd.DataFrame, target: str, config: VerificationConfig
) -> tuple[Backtest, PeriodSeries]:
    """The gate's backtest again, from the same rows and the same plan (deterministic)."""
    periods, values = _series_inputs(frame, target)
    series = period_series(
        periods,
        values,
        aggregate=plan.aggregate,  # type: ignore[arg-type]
        test_start_period=plan.test_start_period,
        max_gap_fraction=plan.max_gap_fraction,
    )
    test = run_backtest(
        series.values,
        method=plan.method,
        season=plan.season,
        horizon=plan.horizon,
        test_start=series.test_start,
        min_train=plan.min_train,
        baseline=plan.baseline,
    )
    return test, series


def forecast_attacks(test: Backtest, config: VerificationConfig) -> list[AttackResult]:
    """F1..F6 on `test`, with the thresholds in `configs/verification.yaml`."""
    return run_forecast_attacks(test, config.attacks, config.forecast)


def forecast_interval(
    test: Backtest, plan: ForecastPlan, config: VerificationConfig
) -> EffectInterval | None:
    """A block-bootstrap interval on the error reduction; None if it cannot be computed."""
    stats = config.statistics
    try:
        low, high = origin_block_interval(
            test.model_loss,
            test.baseline_loss,
            block_length=plan.horizon,
            n_resamples=stats.interval_resamples,
            confidence=stats.interval_confidence,
            seed=stats.seed,
        )
    except ValueError:
        return None
    return EffectInterval(
        estimate=relative_reduction(test.model_loss, test.baseline_loss),
        low=low,
        high=high,
        confidence=stats.interval_confidence,
        method="origin_block_bootstrap",
        n_resamples=stats.interval_resamples,
    )


def forecast_power(payload: dict, config: VerificationConfig) -> PowerNote | None:
    """The smallest error reduction this backtest could have detected, or None.

    Computed from the noise the backtest itself showed (`block_sd` over `n_blocks` blocks) by a
    normal approximation at the run's alpha, before the multiple-testing correction, so a
    corrected test needed a larger reduction. Descriptive; it never gates anything.
    """
    stats = config.statistics
    z = float(
        scipy_stats.norm.ppf(1.0 - stats.alpha / 2.0) + scipy_stats.norm.ppf(stats.power_target)
    )
    found = detectable_reduction(
        block_sd=float(payload["block_sd"]),
        n_blocks=int(payload["n_blocks"]),
        mean_baseline_loss=float(payload["mean_baseline_loss"]),
        z_total=z,
    )
    if found is None or not math.isfinite(found):
        return None
    return PowerNote(
        effect_metric=EffectMetric.MASE_REDUCTION,
        detectable_effect=found,
        n_effective=int(payload["n_blocks"]),
        unit="origin_blocks",
        alpha=stats.alpha,
        target_power=stats.power_target,
    )


def _label(ordinal: int, period: str) -> str:
    return str(pd.Period(ordinal=int(ordinal), freq=_PERIOD_FREQ[period]))


def build_evidence(
    test: Backtest,
    series: PeriodSeries,
    plan: ForecastPlan,
    attacks: list[AttackResult],
    config: VerificationConfig,
) -> ForecastEvidence:
    """The backtest as the card shows it: errors, the per-horizon reductions, the table.

    Guarantees: every number is from `test` (the held-back origins) or from the F4 attack's
    result; the table lists the most recent `MAX_CARD_ORIGINS` origins, one row per horizon.
    """
    period = plan.period
    horizon_reductions = [
        relative_reduction(test.model_loss[:, h], test.baseline_loss[:, h])
        for h in range(test.horizon)
    ]
    versus_last_value: float | None = None
    if plan.baseline != "naive":
        try:
            last_value = with_baseline(test, series.values, "naive")
            versus_last_value = relative_reduction(last_value.model_loss, last_value.baseline_loss)
        except ValueError:
            versus_last_value = None
    f4 = next((a for a in attacks if a.attack_id == "F4"), None)
    stated = stated_interval(test, config.forecast.interval_level)
    rows: list[ForecastOrigin] = []
    for index in range(max(0, test.n_origins - MAX_CARD_ORIGINS), test.n_origins):
        origin_index = int(test.origins[index])
        for h in range(test.horizon):
            rows.append(
                ForecastOrigin(
                    origin=_label(series.ordinals[origin_index - 1], period),
                    target=_label(series.ordinals[origin_index + h], period),
                    horizon=h + 1,
                    actual=float(test.actual[index, h]),
                    forecast=float(test.model[index, h]),
                    baseline=float(test.baseline[index, h]),
                )
            )
    return ForecastEvidence(
        method=plan.method,  # type: ignore[arg-type]
        baseline=plan.baseline,  # type: ignore[arg-type]
        horizon=plan.horizon,
        season=plan.season,
        period=period,
        n_origins=test.n_origins,
        n_blocks=math.ceil(test.n_origins / plan.horizon),
        first_origin=_label(series.ordinals[int(test.origins[0]) - 1], period),
        last_origin=_label(series.ordinals[int(test.origins[-1]) - 1], period),
        mase_model=float(test.model_loss.mean()),
        mase_baseline=float(test.baseline_loss.mean()),
        error_reduction=relative_reduction(test.model_loss, test.baseline_loss),
        horizon_reductions=[float(r) for r in horizon_reductions],
        reduction_vs_last_value=versus_last_value,
        interval_level=config.forecast.interval_level if stated is not None else None,
        interval_coverage=None if stated is None else float(stated[2]),
        interval_calibrated=(
            None if f4 is None or "calibrated" not in f4.details else bool(f4.details["calibrated"])
        ),
        origins=rows,
    )
