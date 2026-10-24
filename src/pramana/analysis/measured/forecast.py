"""M6: a forecast, scored by rolling-origin backtest against a seasonal-naive baseline.

Guarantees: only a table with a time axis is forecast (D12); every backtest origin trains
on periods before it and is scored on the periods after it; the baseline is repeated in
every origin; the headline is the scaled error (MASE) of the better of the two models
against the baseline's, with the origin-to-origin spread; the prediction interval comes
from the backtest's own errors and its coverage is checked leave-one-origin-out; a series
too short for two full seasonal cycles is not modelled seasonally, it is not run, and the
reason is given. The choice between the two models is made on the same backtest, and the
sentence says so.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from pramana.analysis.computed.charts import ForecastChart
from pramana.analysis.measured.common import TITLES, clean, not_run, row, sd
from pramana.analysis.measured.common import label as _label
from pramana.analysis.measured.config import MeasuredConfig
from pramana.analysis.measured.models import MeasuredItem
from pramana.analysis.measured.prep import num
from pramana.analysis.schema_inference import SchemaProfile
from pramana.analysis.shape import DataShape, ShapeProfile, period_keys

_FREQ = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}
_UNIT = {
    "day": "days",
    "week": "weeks",
    "month": "months",
    "quarter": "quarters",
    "year": "years",
    "index": "steps",
}

Forecaster = Callable[[np.ndarray, int], np.ndarray]


def seasonal_naive(m: int) -> Forecaster:
    """Repeat the value one cycle back (or the last value when there is no cycle)."""

    def forecast(train: np.ndarray, h: int) -> np.ndarray:
        if m > 1:
            return np.array([train[len(train) - m + (j % m)] for j in range(h)])
        return np.repeat(train[-1], h)

    return forecast


def holt_winters(m: int) -> Forecaster:
    """Additive exponential smoothing with trend, and a seasonal part when m > 1."""

    def forecast(train: np.ndarray, h: int) -> np.ndarray:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ExponentialSmoothing(
                train,
                trend="add",
                seasonal="add" if m > 1 else None,
                seasonal_periods=m if m > 1 else None,
                initialization_method="estimated",
            ).fit()
            return np.asarray(model.forecast(h), dtype=float)

    return forecast


def trend_dummies(m: int) -> Forecaster:
    """Least-squares line plus a dummy for each position in the cycle (line only if m == 1)."""

    def design(positions: np.ndarray) -> np.ndarray:
        columns = [np.ones(len(positions)), positions.astype(float)]
        if m > 1:
            for k in range(1, m):
                columns.append((positions % m == k).astype(float))
        return np.column_stack(columns)

    def forecast(train: np.ndarray, h: int) -> np.ndarray:
        t = np.arange(len(train))
        coef, *_ = np.linalg.lstsq(design(t), train, rcond=None)
        return design(np.arange(len(train), len(train) + h)) @ coef

    return forecast


def _series(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    target: str,
    additive: bool,
) -> tuple[pd.Series, list[str], int] | None:
    """One value per period in time order, the period labels, and how many periods were
    missing and filled by interpolation. None when the time axis cannot be laid out."""
    assert shape.time_column is not None
    keys, period = period_keys(frame, shape.time_column, schema)
    y = num(frame[target])
    grouped = y.groupby(keys)
    values = (
        grouped.sum(min_count=1)
        if additive and shape.shape is not DataShape.TIME_SERIES
        else (grouped.mean())
    )
    values = values.dropna()
    if values.empty:
        return None
    if period in _FREQ:
        periods = [pd.Period(str(k), freq=_FREQ[period]) for k in values.index]
        ordinals = np.array([p.ordinal for p in periods])
        order = np.argsort(ordinals, kind="stable")
        ordinals, data = ordinals[order], values.to_numpy(dtype=float)[order]
        full = np.arange(ordinals.min(), ordinals.max() + 1)
        series = pd.Series(data, index=ordinals).reindex(full)
        missing = int(series.isna().sum())
        labels = [str(pd.Period(ordinal=int(o), freq=_FREQ[period])) for o in full]
        return series.interpolate().reset_index(drop=True), labels, missing
    ordered = values.sort_index()
    labels = [str(int(k)) if float(k) == int(k) else f"{k:g}" for k in ordered.index]
    return ordered.reset_index(drop=True), labels, 0


def _next_labels(labels: list[str], period: str, h: int) -> list[str]:
    if period in _FREQ:
        last = pd.Period(labels[-1], freq=_FREQ[period])
        return [str(last + k) for k in range(1, h + 1)]
    try:
        last_value = int(float(labels[-1]))
        return [str(last_value + k) for k in range(1, h + 1)]
    except ValueError:
        return [f"+{k}" for k in range(1, h + 1)]


def run_forecast(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    *,
    target: str,
    config: MeasuredConfig,
    additive: bool = True,
) -> MeasuredItem:
    """M6 for one numeric column over the table's time axis."""
    kind = "forecast"
    if shape.time_column is None or shape.shape is DataShape.CROSS_SECTION:
        return not_run(kind, "A forecast needs a date or period column.", target)
    if target not in frame.columns:
        return not_run(kind, f"{target} is not a column of the table.", target)
    laid = _series(frame, schema, shape, target, additive)
    if laid is None:
        return not_run(kind, f"{target} has no values to forecast.", target)
    series, labels, missing = laid
    cfg = config.forecast
    period = shape.period or "index"
    n = len(series)
    if n < cfg.min_periods:
        return not_run(
            kind,
            f"Too few periods to forecast: {n} found, at least {cfg.min_periods} needed.",
            target,
        )
    if missing > cfg.max_gap_fraction * n:
        return not_run(kind, f"{missing} of {n} periods are missing from the series.", target)
    m = cfg.seasonal_length.get(period, 1)
    if m > 1 and n < cfg.min_cycles * m:
        return not_run(
            kind,
            f"Too short to model seasonality: {n} {_UNIT[period]} found, "
            f"{cfg.min_cycles * m} needed ({cfg.min_cycles} full cycles).",
            target,
        )
    h = cfg.horizon.get(period, 1)
    min_train = cfg.min_cycles * m if m > 1 else max(cfg.min_periods // 2, 6)
    n_origins = min(cfg.origins, n - h - min_train + 1)
    if n_origins < cfg.min_origins:
        return not_run(kind, "Too few periods to run a backtest of this length.", target)

    data = series.to_numpy(dtype=float)
    base_fn = seasonal_naive(m)
    lag = m if m > 1 else 1
    candidates: dict[str, Forecaster] = {
        "Holt-Winters exponential smoothing": holt_winters(m),
        "linear trend with seasonal dummies" if m > 1 else "linear trend": trend_dummies(m),
    }
    origins = [n - h - o for o in range(n_origins - 1, -1, -1)]
    errors: dict[str, list[np.ndarray]] = {"baseline": []}
    scaled: dict[str, list[float]] = {"baseline": []}
    percent: dict[str, list[float]] = {"baseline": []}
    scales: list[float] = []
    for name in candidates:
        errors[name], scaled[name], percent[name] = [], [], []
    for t in origins:
        train, actual = data[:t], data[t : t + h]
        scale = float(np.mean(np.abs(train[lag:] - train[:-lag])))
        if scale == 0:
            return not_run(
                kind, f"{target} is constant, so a forecast error cannot be scaled.", target
            )
        scales.append(scale)
        for name, fn in {"baseline": base_fn, **candidates}.items():
            try:
                predicted = fn(train, h)
            except Exception:
                errors.pop(name, None)
                scaled.pop(name, None)
                percent.pop(name, None)
                continue
            if name not in errors:
                continue
            err = actual - predicted
            errors[name].append(err)
            scaled[name].append(float(np.mean(np.abs(err)) / scale))
            if np.all(actual != 0):
                percent[name].append(float(np.mean(np.abs(err) / np.abs(actual))))
    usable = [name for name in candidates if name in scaled and len(scaled[name]) == len(origins)]
    if not usable:
        return not_run(kind, "No forecasting method could be fitted to this series.", target)
    mase = {name: float(np.mean(scaled[name])) for name in ["baseline", *usable]}
    best = min(usable, key=lambda name: mase[name])
    gap = [b - m_ for b, m_ in zip(scaled["baseline"], scaled[best], strict=True)]
    lift, spread = mase["baseline"] - mase[best], sd(gap)
    relative = lift / mase["baseline"] if mase["baseline"] > 0 else 0.0
    baseline_name = "seasonal-naive" if m > 1 else "last-value"
    split_text = f"rolling-origin backtest {len(origins)} origins, {h} {_UNIT[period]} ahead"

    # interval from the backtest errors, coverage checked leaving one origin out
    matrix = np.vstack(errors[best])
    low_q, high_q = (1 - cfg.interval_level) / 2, (1 + cfg.interval_level) / 2
    pooled = matrix.ravel()
    lo, hi = np.quantile(pooled, [low_q, high_q])
    covered = []
    for o in range(len(matrix)):
        rest = np.delete(matrix, o, axis=0).ravel()
        a, b = np.quantile(rest, [low_q, high_q])
        covered.append(float(np.mean((matrix[o] >= a) & (matrix[o] <= b))))
    coverage = float(np.mean(covered))

    next_fn = candidates[best]
    future = np.asarray(next_fn(data, h), dtype=float)
    future_labels = _next_labels(labels, period, h)
    keep = cfg.max_chart_points
    chart = ForecastChart(
        x_label="Period",
        y_label=_label(target),
        interval_level=cfg.interval_level,
        actual=[(lab, float(v)) for lab, v in zip(labels[-keep:], data[-keep:], strict=True)],
        forecast=[(lab, float(v)) for lab, v in zip(future_labels, future, strict=True)],
        lower=[(lab, float(v + lo)) for lab, v in zip(future_labels, future, strict=True)],
        upper=[(lab, float(v + hi)) for lab, v in zip(future_labels, future, strict=True)],
    )
    values = {
        "periods": n,
        "filled_periods": missing,
        "seasonal_length": m,
        "horizon": h,
        "origins": len(origins),
        "mase_baseline": mase["baseline"],
        "mase_model": mase[best],
        "error_reduction_pct": relative * 100,
        "lift_floor_relative_pct": cfg.lift_floor_relative * 100,
        "interval_level": cfg.interval_level,
        "interval_backtest_coverage": coverage,
        "interval_lower_offset": float(lo),
        "interval_upper_offset": float(hi),
        "mape_baseline": float(np.mean(percent["baseline"])) if percent["baseline"] else None,
        "mape_model": float(np.mean(percent[best])) if percent.get(best) else None,
    }
    for name in usable:
        values[f"mase {name}"] = mase[name]
    common = dict(
        id=f"{kind}:{target}",
        kind=kind,
        title=f"{TITLES[kind]}: {_label(target)}",
        target=target,
        model_family=best,
        models_tried=len(candidates),
        split=split_text,
        baseline=baseline_name,
        metric="MASE",
        baseline_score=mase["baseline"],
        model_score=mase[best],
        lift=lift,
        spread=spread,
        n_rows=n,
        values={k: clean(v) for k, v in values.items()},
    )
    if relative < cfg.lift_floor_relative:
        return MeasuredItem(
            status="no_lift",
            sentence=(
                f"No forecasting method beat the {baseline_name} baseline in the backtest: the "
                f"best was {relative * 100:.0f}% lower in error, against a floor of "
                f"{cfg.lift_floor_relative * 100:.0f}%."
            ),
            **common,
        )
    return MeasuredItem(
        status="ok",
        sentence=(
            f"{best[0].upper() + best[1:]} forecasts {_label(target)} {h} {_UNIT[period]} ahead "
            f"with {relative * 100:.0f}% less error than the {baseline_name} baseline on periods "
            f"it did not see (scaled error {mase[best]:.2f} against {mase['baseline']:.2f}, "
            f"± {spread:.2f} between origins; {split_text}). It is the better of "
            f"{len(candidates)} methods, picked on the same backtest. The "
            f"{cfg.interval_level * 100:.0f}% interval covered {coverage * 100:.0f}% of "
            "backtest values."
        ),
        table=[
            row(period=lab, forecast=float(v), lower=float(v + lo), upper=float(v + hi))
            for lab, v in zip(future_labels, future, strict=True)
        ],
        chart=chart,
        **common,
    )
