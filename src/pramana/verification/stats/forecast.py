"""Forecast claims: a rolling-origin backtest and a block sign-flip test against seasonal-naive.

The claim being tested is about PAST OUT-OF-SAMPLE ACCURACY, never about the future: "this
method beat a seasonal-naive forecast on periods it did not see". Everything here follows
from that sentence.

  * `period_series`     -- rows to one value per period, in time order; a gap in the held-back
                           window is refused, a gap in the history is carried forward from the
                           PAST only, so no filled value ever depends on a later one.
  * `run_backtest`      -- for each origin t and horizon h = 1..H the method is fitted on the
                           values BEFORE t and scored on t..t+H-1. The fit is handed a
                           read-only copy of the history, so a method cannot see the future.
                           Origins start at the first held-back period, so every scored
                           period is one the proposer never saw.
  * `forecast_loss_test`-- the p-value. Each origin has a scaled loss for the method and for
                           the baseline (MASE-style: absolute error over the in-sample
                           seasonal-naive MAE). Under the null "the method is no better than
                           the baseline" the two losses of an origin are exchangeable, so the
                           null swaps them. Neighbouring origins share their forecast horizon
                           and are dependent, so the swap is made for a whole block of
                           `block_length` origins at once (one block = one forecast horizon).
                           The statistic is the relative error reduction
                           `1 - sum(method loss) / sum(baseline loss)`; the p-value doubles
                           the smaller tail, which is the same answer in any monotone scale.

Nothing here claims the next periods will behave like the tested ones. A structural break,
a new product or a changed calendar defeats any backtest.

Owner: P.P. Satya Karthikeya
Scope: docs/evidence/FORECAST_CLAIM_2026-10-25.md
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike, NDArray

from pramana.contracts.enums import PermutationScheme
from pramana.contracts.forecast import METHOD_LABELS as _CONTRACT_LABELS
from pramana.verification.stats.permutation import (
    _TOLERANCE,
    PermutationResult,
    _stamped,
    _validate_run,
)

#: The closed menu of methods a forecast claim may name. Code picks one on exploration rows.
FORECAST_METHODS: tuple[str, ...] = ("trend_seasonal", "holt_winters")

#: How each method is named in a claim sentence (the same names the Measured tier uses).
METHOD_LABELS = _CONTRACT_LABELS

Forecaster = Callable[[NDArray[np.float64], int], NDArray[np.float64]]
Aggregate = Literal["sum", "mean"]


def seasonal_naive(season: int) -> Forecaster:
    """Repeat the value one cycle back; the last value when there is no full cycle yet."""

    def forecast(train: NDArray[np.float64], horizon: int) -> NDArray[np.float64]:
        if season > 1 and train.size >= season:
            return np.array([train[train.size - season + (j % season)] for j in range(horizon)])
        return np.repeat(train[-1], horizon)

    return forecast


def trend_seasonal(season: int) -> Forecaster:
    """Least-squares line plus a dummy for each position in the cycle (line only if season == 1)."""

    def design(positions: NDArray[np.int64], seasonal: bool) -> NDArray[np.float64]:
        columns = [np.ones(positions.size), positions.astype(float)]
        if seasonal:
            columns += [(positions % season == k).astype(float) for k in range(1, season)]
        return np.column_stack(columns)

    def forecast(train: NDArray[np.float64], horizon: int) -> NDArray[np.float64]:
        seasonal = season > 1 and train.size >= season + 2
        t = np.arange(train.size)
        coef, *_ = np.linalg.lstsq(design(t, seasonal), train, rcond=None)
        return design(np.arange(train.size, train.size + horizon), seasonal) @ coef

    return forecast


def holt_winters(season: int) -> Forecaster:
    """Additive exponential smoothing with trend, and a seasonal part when season > 1."""

    def forecast(train: NDArray[np.float64], horizon: int) -> NDArray[np.float64]:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        seasonal = season > 1 and train.size >= 2 * season
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ExponentialSmoothing(
                train,
                trend="add",
                seasonal="add" if seasonal else None,
                seasonal_periods=season if seasonal else None,
                initialization_method="estimated",
            ).fit()
            return np.asarray(model.forecast(horizon), dtype=float)

    return forecast


def forecaster_for(method: str, season: int) -> Forecaster:
    """The forecaster a claim names, or a refusal for a name outside the closed menu."""
    if method == "trend_seasonal":
        return trend_seasonal(season)
    if method == "holt_winters":
        return holt_winters(season)
    raise ValueError(
        f"{method!r} is not a forecasting method this gate can test; "
        f"the menu is {list(FORECAST_METHODS)}"
    )


# --- rows to a series ------------------------------------------------------------


@dataclass(frozen=True)
class PeriodSeries:
    """One value per period, in time order, and where the held-back window starts."""

    ordinals: NDArray[np.int64]
    values: NDArray[np.float64]
    test_start: int
    filled: int


def period_series(
    periods: ArrayLike,
    values: ArrayLike,
    *,
    aggregate: Aggregate,
    test_start_period: float,
    max_gap_fraction: float,
) -> PeriodSeries:
    """The series of period totals (or means), laid out over every period in its range.

    Guarantees: sorted by period; a period with no value inside the held-back window
    (`>= test_start_period`) raises, because scoring against an invented actual is not
    scoring; a gap in the history is filled by carrying the last earlier value forward, so
    no filled value depends on a later one; more missing periods than
    `max_gap_fraction` of the range raises. `ValueError` messages are written for the user.
    """
    frame = pd.DataFrame(
        {
            "p": np.round(np.asarray(periods, dtype=float)),
            "v": np.asarray(values, dtype=float),
        }
    ).dropna()
    if frame.empty:
        raise ValueError("there are no values to forecast")
    grouped = frame.groupby("p")["v"]
    per_period = grouped.sum() if aggregate == "sum" else grouped.mean()
    ordinals = per_period.index.to_numpy(dtype=np.int64)
    full = np.arange(ordinals.min(), ordinals.max() + 1)
    series = per_period.reindex(full)
    missing = series.isna().to_numpy()
    start = int(np.searchsorted(full, int(round(test_start_period)), side="left"))
    if not 0 < start < full.size:
        raise ValueError("the held-back window is empty or is the whole series")
    if missing[start:].any():
        raise ValueError(
            "a period inside the held-back window has no value, so it cannot be scored"
        )
    if missing.sum() > max_gap_fraction * full.size:
        raise ValueError(f"{int(missing.sum())} of {full.size} periods are missing from the series")
    return PeriodSeries(
        ordinals=full,
        values=series.ffill().to_numpy(dtype=float),
        test_start=start,
        filled=int(missing.sum()),
    )


# --- the backtest ------------------------------------------------------------------


BASELINES: tuple[str, ...] = ("seasonal_naive", "naive")


@dataclass(frozen=True)
class Backtest:
    """Every origin's forecasts, the baseline's and the actuals, all scored on unseen periods.

    `actual`, `model` and `baseline` have one row per origin and one column per horizon.
    `scale` is each origin's in-sample MAE of the baseline's own rule (the MASE denominator).
    """

    method: str
    baseline_kind: str
    season: int
    horizon: int
    origins: NDArray[np.int64]
    scale: NDArray[np.float64]
    actual: NDArray[np.float64]
    model: NDArray[np.float64]
    baseline: NDArray[np.float64]

    @property
    def model_loss(self) -> NDArray[np.float64]:
        return np.abs(self.actual - self.model) / self.scale[:, None]

    @property
    def baseline_loss(self) -> NDArray[np.float64]:
        return np.abs(self.actual - self.baseline) / self.scale[:, None]

    @property
    def n_origins(self) -> int:
        return int(self.origins.size)


def run_backtest(
    values: ArrayLike,
    *,
    method: str,
    season: int,
    horizon: int,
    test_start: int,
    min_train: int,
    baseline: str = "seasonal_naive",
    forecaster: Forecaster | None = None,
) -> Backtest:
    """Fit on the periods before each origin and score the next `horizon` periods.

    Guarantees: origin t is fitted on `values[:t]` only (a read-only copy) and the origins
    run from `max(test_start, min_train)` to the last origin with `horizon` periods after
    it, so no scored period is earlier than `test_start`; the baseline is seasonal-naive
    (the last value when the history is shorter than one cycle) or, when `baseline` is
    "naive", the last value; raises when there is no origin, or when the baseline's
    in-sample MAE is zero (a constant series cannot be scaled). `forecaster` exists for
    the leakage test; callers name a `method`.
    """
    if baseline not in BASELINES:
        raise ValueError(f"{baseline!r} is not a baseline; the menu is {list(BASELINES)}")
    y = np.asarray(values, dtype=float).ravel()
    if horizon < 1:
        raise ValueError("the horizon must be at least 1")
    first = max(test_start, min_train)
    origins = np.arange(first, y.size - horizon + 1)
    if origins.size == 0:
        raise ValueError("the series is too short for a single backtest origin")
    fit = forecaster or forecaster_for(method, season)
    base_season = season if baseline == "seasonal_naive" else 1
    naive = seasonal_naive(base_season)
    lag = base_season if base_season > 1 else 1
    scale = np.empty(origins.size)
    actual = np.empty((origins.size, horizon))
    model = np.empty_like(actual)
    base = np.empty_like(actual)
    for i, t in enumerate(origins):
        history = y[:t].copy()
        history.setflags(write=False)
        denominator = float(np.mean(np.abs(history[lag:] - history[:-lag])))
        if not denominator > 0.0 or not math.isfinite(denominator):
            raise ValueError("the series is constant before an origin, so errors cannot be scaled")
        scale[i] = denominator
        actual[i] = y[t : t + horizon]
        model[i] = np.asarray(fit(history, horizon), dtype=float)
        base[i] = naive(history, horizon)
    if not np.all(np.isfinite(model)):
        raise ValueError("the method returned a non-finite forecast")
    return Backtest(method, baseline, season, horizon, origins, scale, actual, model, base)


def with_baseline(test: Backtest, values: ArrayLike, baseline: str) -> Backtest:
    """The same backtest scored against another baseline, without fitting the method again.

    Guarantees: the method's forecasts and the actuals are exactly `test`'s; the baseline's
    forecasts and the MASE scale are recomputed from `values[:origin]` for every origin, so the
    result is what `run_backtest(..., baseline=baseline)` would give.
    """
    if baseline not in BASELINES:
        raise ValueError(f"{baseline!r} is not a baseline; the menu is {list(BASELINES)}")
    y = np.asarray(values, dtype=float).ravel()
    base_season = test.season if baseline == "seasonal_naive" else 1
    naive = seasonal_naive(base_season)
    lag = base_season if base_season > 1 else 1
    scale = np.empty(test.n_origins)
    base = np.empty_like(test.actual)
    for i, t in enumerate(test.origins):
        history = y[:t]
        denominator = float(np.mean(np.abs(history[lag:] - history[:-lag])))
        if not denominator > 0.0 or not math.isfinite(denominator):
            raise ValueError("the series is constant before an origin, so errors cannot be scaled")
        scale[i] = denominator
        base[i] = naive(history, test.horizon)
    return Backtest(
        test.method,
        baseline,
        test.season,
        test.horizon,
        test.origins,
        scale,
        test.actual,
        test.model,
        base,
    )


def relative_reduction(model_loss: ArrayLike, baseline_loss: ArrayLike) -> float:
    """`1 - sum(model loss) / sum(baseline loss)`: the share of the baseline's error removed.

    Positive when the method beat the baseline, negative when it was worse; the MASE ratio is
    `1 - reduction`. Raises for a baseline with no error at all.
    """
    base = float(np.sum(baseline_loss))
    if not base > 0.0:
        raise ValueError("the baseline has no error, so a reduction is undefined")
    return 1.0 - float(np.sum(model_loss)) / base


# --- the test ---------------------------------------------------------------------


def _origin_losses(loss: NDArray[np.float64]) -> NDArray[np.float64]:
    """Sum over horizons: one number per origin."""
    return loss.sum(axis=1) if loss.ndim == 2 else loss


def forecast_loss_test(
    model_loss: ArrayLike,
    baseline_loss: ArrayLike,
    *,
    block_length: int,
    n_permutations: int,
    seed: int,
) -> PermutationResult:
    """Block sign-flip (swap) test that the method is no better than the baseline.

    Guarantees: the statistic is `relative_reduction` of the observed losses and does not
    depend on the seed; each resample swaps the method's and the baseline's loss for every
    origin of a randomly chosen set of whole blocks of `block_length` consecutive origins
    (a swap is a sign flip of the loss difference); the p-value is two-sided by doubling
    the smaller add-one tail, so it is never below `2 / (n_permutations + 1)` and never
    above 1; stamped `BLOCK_SIGN_FLIP`. Raises for fewer than two blocks.
    """
    _validate_run(n_permutations, "two-sided")
    lm = _origin_losses(np.asarray(model_loss, dtype=float))
    lb = _origin_losses(np.asarray(baseline_loss, dtype=float))
    if lm.shape != lb.shape or lm.ndim != 1:
        raise ValueError("the method and the baseline need one loss per origin each")
    if block_length < 1:
        raise ValueError("block_length must be at least 1")
    blocks = np.arange(lm.size) // block_length
    n_blocks = int(blocks[-1]) + 1
    if n_blocks < 2:
        raise ValueError(f"{n_blocks} block of origins is too few to test")
    observed = relative_reduction(lm, lb)
    rng = np.random.default_rng(seed)
    swap = rng.integers(0, 2, size=(n_permutations, n_blocks), dtype=np.int8)[:, blocks].astype(
        bool
    )
    method_total = np.where(swap, lb, lm).sum(axis=1)
    baseline_total = np.where(swap, lm, lb).sum(axis=1)
    null = 1.0 - method_total / baseline_total
    at_least = int(np.count_nonzero(null >= observed - _TOLERANCE))
    at_most = int(np.count_nonzero(null <= observed + _TOLERANCE))
    tail = (1 + min(at_least, at_most)) / (n_permutations + 1)
    return _stamped(
        min(1.0, 2.0 * tail),
        observed,
        n_permutations,
        seed,
        PermutationScheme.BLOCK_SIGN_FLIP,
    )


@dataclass(frozen=True)
class ForecastTest:
    """What the test computed beside the p-value, for the proof and the power note."""

    result: PermutationResult
    series: PeriodSeries
    backtest: Backtest
    mase_model: float
    mase_baseline: float
    n_blocks: int
    block_sd: float
    mean_baseline_loss: float


def forecast_claim_test(
    periods: ArrayLike,
    values: ArrayLike,
    *,
    method: str,
    baseline: str,
    aggregate: Aggregate,
    season: int,
    horizon: int,
    test_start_period: float,
    min_train: int,
    max_gap_fraction: float,
    block_length: int,
    n_permutations: int,
    seed: int,
) -> ForecastTest:
    """The whole claim test on rows: one value per period, backtest, then the sign-flip test.

    Guarantees: the series is `period_series` (no value filled from the future, nothing
    invented inside the held-back window), the backtest is `run_backtest` (no leakage,
    held-back origins only) and the p-value is `forecast_loss_test` on its scaled losses.
    `mase_*` are mean scaled absolute errors over every origin and horizon. `block_sd` is the
    standard deviation, across blocks, of the mean loss difference per origin: the noise level
    the detectable-effect note uses.
    """
    series = period_series(
        periods,
        values,
        aggregate=aggregate,
        test_start_period=test_start_period,
        max_gap_fraction=max_gap_fraction,
    )
    test = run_backtest(
        series.values,
        method=method,
        season=season,
        horizon=horizon,
        test_start=series.test_start,
        min_train=min_train,
        baseline=baseline,
    )
    lm, lb = test.model_loss, test.baseline_loss
    result = forecast_loss_test(
        lm, lb, block_length=block_length, n_permutations=n_permutations, seed=seed
    )
    difference = _origin_losses(lb) - _origin_losses(lm)
    blocks = np.arange(difference.size) // block_length
    block_means = np.array([difference[blocks == b].mean() for b in np.unique(blocks)])
    return ForecastTest(
        result=result,
        series=series,
        backtest=test,
        mase_model=float(lm.mean()),
        mase_baseline=float(lb.mean()),
        n_blocks=int(block_means.size),
        block_sd=float(block_means.std(ddof=1)) if block_means.size > 1 else 0.0,
        mean_baseline_loss=float(_origin_losses(lb).mean()),
    )


def origin_block_interval(
    model_loss: ArrayLike,
    baseline_loss: ArrayLike,
    *,
    block_length: int,
    n_resamples: int,
    confidence: float,
    seed: int,
) -> tuple[float, float]:
    """A percentile interval on the error reduction, resampling whole blocks of origins.

    Guarantees: deterministic for a seed; the unit resampled is a block of `block_length`
    consecutive origins, so the overlap between neighbouring origins is not treated as extra
    independent evidence. Descriptive: nothing here gates a verdict.
    """
    lm = _origin_losses(np.asarray(model_loss, dtype=float))
    lb = _origin_losses(np.asarray(baseline_loss, dtype=float))
    blocks = np.arange(lm.size) // block_length
    members = [np.flatnonzero(blocks == b) for b in np.unique(blocks)]
    rng = np.random.default_rng(seed)
    reductions = []
    for _ in range(n_resamples):
        chosen = rng.integers(0, len(members), size=len(members))
        take = np.concatenate([members[i] for i in chosen])
        base = float(lb[take].sum())
        if base > 0.0:
            reductions.append(1.0 - float(lm[take].sum()) / base)
    tail = (1.0 - confidence) / 2.0
    low, high = np.quantile(reductions, [tail, 1.0 - tail])
    return float(low), float(high)


def detectable_reduction(
    *, block_sd: float, n_blocks: int, mean_baseline_loss: float, z_total: float
) -> float | None:
    """The smallest error reduction this backtest could have detected, by a normal approximation.

    `z_total` is `z(1 - alpha/2) + z(power)`. The standard error of the mean loss difference is
    taken from the blocks' own spread, so it is an estimate from this very backtest, descriptive
    and not a simulation of the gate. None when it cannot be worked out.
    """
    if n_blocks < 2 or not mean_baseline_loss > 0.0 or not math.isfinite(block_sd):
        return None
    difference = z_total * block_sd / math.sqrt(n_blocks)
    reduction = difference / mean_baseline_loss
    return float(reduction) if reduction > 0.0 and math.isfinite(reduction) else None
