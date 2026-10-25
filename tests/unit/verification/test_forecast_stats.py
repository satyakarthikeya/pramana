"""Known-answer tests for the forecast backtest and its block sign-flip test."""

from __future__ import annotations

import numpy as np
import pytest

from pramana.contracts.enums import PermutationScheme
from pramana.verification.stats.forecast import (
    forecast_loss_test,
    origin_block_interval,
    period_series,
    relative_reduction,
    run_backtest,
    seasonal_naive,
    trend_seasonal,
)


def _seasonal(n: int, noise: float = 0.0, seed: int = 0) -> np.ndarray:
    t = np.arange(n)
    rng = np.random.default_rng(seed)
    return 100 + 0.5 * t + 10 * np.sin(2 * np.pi * t / 12) + rng.normal(0, noise, n)


# --- the statistic -------------------------------------------------------------


def test_relative_reduction_known_answer() -> None:
    # method loses 1 each of 4 origins, baseline 2 each: half the error removed
    assert relative_reduction([1, 1, 1, 1], [2, 2, 2, 2]) == pytest.approx(0.5)
    assert relative_reduction([3, 3], [2, 2]) == pytest.approx(-0.5)
    with pytest.raises(ValueError):
        relative_reduction([1], [0])


def test_seasonal_naive_repeats_last_cycle_and_falls_back_to_last_value() -> None:
    y = np.arange(1.0, 25.0)
    assert list(seasonal_naive(12)(y, 3)) == [13.0, 14.0, 15.0]
    assert list(seasonal_naive(12)(y[:5], 2)) == [5.0, 5.0]  # shorter than a cycle
    assert list(seasonal_naive(1)(y, 2)) == [24.0, 24.0]


def test_trend_seasonal_is_exact_on_a_noiseless_trend_plus_season() -> None:
    y = _seasonal(48)
    forecast = trend_seasonal(12)(y[:36], 2)
    assert forecast == pytest.approx(y[36:38], abs=1e-6)


# --- the test: planted null and planted better model ----------------------------


def test_planted_null_gives_a_high_p_and_never_below_the_floor() -> None:
    rng = np.random.default_rng(5)
    ps = []
    for _ in range(40):
        a = rng.exponential(1.0, 30)
        b = rng.exponential(1.0, 30)  # same distribution: exchangeable by construction
        ps.append(forecast_loss_test(a, b, block_length=1, n_permutations=999, seed=1).p_value)
    assert np.mean(np.array(ps) <= 0.05) <= 0.12  # alpha 0.05 with 40 draws of noise
    assert min(ps) >= 2 / 1000


def test_planted_better_model_gives_a_low_p_and_positive_effect() -> None:
    rng = np.random.default_rng(6)
    base = rng.uniform(1.0, 2.0, 30)
    model = 0.5 * base
    result = forecast_loss_test(model, base, block_length=2, n_permutations=999, seed=1)
    assert result.p_value < 0.01
    assert result.statistic == pytest.approx(0.5)
    assert result.scheme is PermutationScheme.BLOCK_SIGN_FLIP


def test_planted_worse_model_has_a_negative_effect_and_a_low_p() -> None:
    base = np.linspace(1.0, 2.0, 30)
    result = forecast_loss_test(2 * base, base, block_length=2, n_permutations=999, seed=1)
    assert result.statistic < 0
    assert result.p_value < 0.01


def test_test_is_deterministic_for_a_seed_and_refuses_one_block() -> None:
    a, b = np.linspace(1, 2, 20), np.linspace(1.2, 2.4, 20)
    one = forecast_loss_test(a, b, block_length=2, n_permutations=500, seed=9)
    two = forecast_loss_test(a, b, block_length=2, n_permutations=500, seed=9)
    assert one.p_value == two.p_value
    with pytest.raises(ValueError):
        forecast_loss_test(a[:3], b[:3], block_length=5, n_permutations=500, seed=9)


def test_swapping_is_by_whole_blocks() -> None:
    # losses where only the pairing inside a block could distinguish the draws: with block 20
    # (one block) the procedure is refused; with 10 blocks of 2 it runs
    a, b = np.linspace(1, 2, 20), np.linspace(1.2, 2.4, 20)
    with pytest.raises(ValueError):
        forecast_loss_test(a, b, block_length=20, n_permutations=500, seed=1)
    assert forecast_loss_test(a, b, block_length=2, n_permutations=500, seed=1).p_value > 0


def test_block_interval_contains_the_estimate_for_a_clear_effect() -> None:
    rng = np.random.default_rng(1)
    base = rng.uniform(1, 2, 40)
    low, high = origin_block_interval(
        0.6 * base, base, block_length=2, n_resamples=300, confidence=0.95, seed=3
    )
    assert low <= 0.4 <= high


# --- the series ------------------------------------------------------------------


def test_period_series_sums_fills_the_past_and_refuses_a_gap_in_the_test_window() -> None:
    periods = [1, 1, 2, 4, 5, 6]
    values = [1, 2, 10, 20, 30, 40]
    out = period_series(periods, values, aggregate="sum", test_start_period=5, max_gap_fraction=0.5)
    assert list(out.values) == [3, 10, 10, 20, 30, 40]  # period 3 carried forward from 2
    assert out.filled == 1 and out.test_start == 4
    with pytest.raises(ValueError, match="held-back window"):
        period_series(
            [1, 2, 3, 6], [1, 1, 1, 1], aggregate="mean", test_start_period=4, max_gap_fraction=0.9
        )
    with pytest.raises(ValueError, match="missing"):
        period_series(
            [1, 2, 6, 7], [1, 1, 1, 1], aggregate="mean", test_start_period=6, max_gap_fraction=0.1
        )


# --- no leakage ---------------------------------------------------------------------


def test_each_origin_is_fitted_on_the_past_only() -> None:
    y = _seasonal(60, noise=2.0)
    seen: list[int] = []

    def spy(train: np.ndarray, horizon: int) -> np.ndarray:
        seen.append(train.size)
        assert not train.flags.writeable  # the method cannot even edit its history
        return np.repeat(train[-1], horizon)

    test = run_backtest(
        y,
        method="trend_seasonal",
        season=12,
        horizon=2,
        test_start=30,
        min_train=24,
        forecaster=spy,
    )
    assert seen == [int(t) for t in test.origins]
    assert test.origins[0] == 30 and test.origins[-1] == 58
    # every scored period is at or after the first held-back period
    assert test.actual[0, 0] == y[30]


def test_changing_the_future_never_changes_an_earlier_forecast() -> None:
    y = _seasonal(60, noise=2.0)
    changed = y.copy()
    changed[40:] += 1000.0  # a different future from period 40 on
    a = run_backtest(y, method="trend_seasonal", season=12, horizon=2, test_start=30, min_train=24)
    b = run_backtest(
        changed, method="trend_seasonal", season=12, horizon=2, test_start=30, min_train=24
    )
    # origins 30..38 forecast periods before 40 only from history before 40: identical forecasts
    for i, origin in enumerate(a.origins):
        if origin + 2 <= 40:
            assert np.array_equal(a.model[i], b.model[i])
            assert np.array_equal(a.baseline[i], b.baseline[i])


def test_a_constant_history_is_refused_rather_than_scaled() -> None:
    with pytest.raises(ValueError, match="constant"):
        run_backtest(
            np.ones(60), method="trend_seasonal", season=12, horizon=1, test_start=30, min_train=24
        )


def test_rescoring_against_another_baseline_equals_a_fresh_backtest() -> None:
    from pramana.verification.stats.forecast import with_baseline

    y = _seasonal(60, noise=2.0, seed=4)
    kwargs = dict(method="trend_seasonal", season=12, horizon=2, test_start=30, min_train=24)
    fresh = run_backtest(y, baseline="naive", **kwargs)
    rescored = with_baseline(run_backtest(y, baseline="seasonal_naive", **kwargs), y, "naive")
    assert np.array_equal(fresh.baseline, rescored.baseline)
    assert np.array_equal(fresh.scale, rescored.scale)
    assert np.array_equal(fresh.model, rescored.model)
