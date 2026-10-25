"""Forecast claims through admissibility, the gateway, the attacks and the wording."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.api.v1 import rejection_reason
from pramana.contracts import (
    CandidateInsight,
    ClaimType,
    DataStructure,
    Direction,
    ForecastSpec,
    GateOutcome,
    PermutationScheme,
    ProofObject,
    TableShape,
    Verdict,
    render_forecast_claim,
)
from pramana.contracts.attack import AttackOutcome
from pramana.verification.admissibility import (
    FORECAST_REFUSED_TERMS,
    TESTABLE_CLAIM_TYPES,
    screen,
)
from pramana.verification.attacks.forecast import run_forecast_attacks
from pramana.verification.config import ClaimsConfig, VerificationConfig, load_config
from pramana.verification.falsification.generator import GeneratorError, generate_from_llm
from pramana.verification.gateway import verify_batch, verify_batch_with_summary
from pramana.verification.schemes import split_rows
from pramana.verification.stats.forecast import Backtest
from tests.fixtures.config import load_pinned_config

STRUCTURE = DataStructure(
    shape=TableShape.TIME_SERIES, time_column="month", period="month", declared_by="caller"
)


def _config(*, enabled: bool = True) -> VerificationConfig:
    shipped = load_pinned_config()
    return shipped.model_copy(
        update={
            "claims": ClaimsConfig(forecast_enabled=enabled),
            "statistics": shipped.statistics.model_copy(update={"n_permutations": 999}),
        }
    )


def _series(shape: str, n: int, seed: int) -> pd.DataFrame:
    t = np.arange(n)
    rng = np.random.default_rng(seed)
    seasonal = 10 * np.sin(2 * np.pi * t / 12) + 4 * np.cos(2 * np.pi * t / 6)
    if shape == "true":
        y = 100 + 0.5 * t + seasonal + rng.normal(0, 2, n)
    else:  # seasonal random walk: nothing beats seasonal-naive
        y = np.zeros(n)
        y[:12] = rng.normal(0, 5, 12)
        for i in range(12, n):
            y[i] = y[i - 12] + rng.normal(0, 2)
        y = 100 + y
    return pd.DataFrame(
        {"month": pd.period_range("2019-01", periods=n, freq="M").to_timestamp(), "revenue": y}
    )


def _candidate(
    spec: ForecastSpec | None = None,
    *,
    claim: str | None = None,
    direction: Direction | None = Direction.POSITIVE,
    insight_id: str = "fc1",
) -> CandidateInsight:
    spec = spec or ForecastSpec(horizon=2, method="trend_seasonal", baseline="seasonal_naive")
    return CandidateInsight(
        insight_id=insight_id,
        claim=claim or render_forecast_claim("revenue", spec),
        claim_type=ClaimType.FORECAST,
        variables=["month", "revenue"],
        dataset_ref="x",
        asserted_direction=direction,
        forecast=spec,
    )


def _run(frame: pd.DataFrame, config: VerificationConfig, candidates=None):
    explore, confirm, record = split_rows(frame, STRUCTURE, config)
    return verify_batch_with_summary(
        candidates or [_candidate()],
        frame.iloc[confirm].reset_index(drop=True),
        config,
        structure=STRUCTURE,
        split=record,
        history=frame.iloc[explore].reset_index(drop=True),
    )


# --- flag off: nothing about existing behaviour changes -----------------------------


def test_the_shipped_flag_is_off_and_the_testable_set_is_unchanged() -> None:
    assert load_config().claims.forecast_enabled is False
    assert ClaimType.FORECAST not in TESTABLE_CLAIM_TYPES
    assert len(TESTABLE_CLAIM_TYPES) == 5


def test_with_the_flag_off_a_forecast_claim_is_refused_and_nothing_runs() -> None:
    result = screen(_candidate(), ["month", "revenue"])
    assert not result.admissible and "switched off" in (result.reason or "")
    proofs, summary = _run(_series("true", 96, 1), _config(enabled=False))
    assert proofs[0].gate_outcome is GateOutcome.NOT_TESTABLE
    assert "switched off" in (proofs[0].failure_reason or "")
    assert summary.n_tested == 0


def test_the_distribution_refusal_text_is_the_one_it_always_was() -> None:
    odd = CandidateInsight(
        insight_id="d",
        claim="x is spread widely",
        claim_type=ClaimType.DISTRIBUTION,
        variables=["a", "b"],
        dataset_ref="x",
    )
    reason = screen(odd, ["a", "b"]).reason or ""
    assert (
        "supported types are correlation, group_difference, period_change, seasonality, trend"
        in reason
    )


# --- the words a backtest cannot support -------------------------------------------


@pytest.mark.parametrize("word", ["proven", "will be", "guaranteed", "true", "correct"])
def test_forecast_claims_that_say_proven_or_will_be_are_refused(word: str) -> None:
    assert word in FORECAST_REFUSED_TERMS
    text = f"A forecast of revenue is {word} to beat a seasonal-naive forecast"
    result = screen(_candidate(claim=text), ["month", "revenue"], forecast_enabled=True)
    assert not result.admissible
    assert "cannot support" in (result.reason or "") or "universal" in (result.reason or "")


def test_the_rendered_sentence_is_admissible_and_uses_none_of_those_words() -> None:
    candidate = _candidate()
    for baseline in ("seasonal_naive", "naive"):
        for method in ("trend_seasonal", "holt_winters"):
            text = render_forecast_claim(
                "revenue", ForecastSpec(horizon=3, method=method, baseline=baseline)
            )
            assert not any(f" {word} " in f" {text.lower()} " for word in FORECAST_REFUSED_TERMS)
    assert screen(candidate, ["month", "revenue"], forecast_enabled=True).admissible
    assert candidate.claim == (
        "A forecast of revenue by linear trend with seasonal dummies beats a seasonal-naive "
        "forecast, measured on periods it did not see, over 2 periods ahead."
    )


def test_a_sentence_not_written_by_code_or_without_a_positive_direction_is_refused() -> None:
    other = "A forecast of revenue by linear trend with seasonal dummies is quite good"
    assert not screen(
        _candidate(claim=other), ["month", "revenue"], forecast_enabled=True
    ).admissible
    undirected = _candidate(direction=None)
    assert not screen(undirected, ["month", "revenue"], forecast_enabled=True).admissible


def test_the_llm_generator_refuses_a_forecast_claim_and_never_falls_back() -> None:
    config = _config()
    llm = config.model_copy(update={"llm": config.llm.model_copy(update={"generator": "llm"})})
    with pytest.raises(GeneratorError, match="vetted template only"):
        generate_from_llm(_candidate(), llm)


# --- the gateway: planted true, planted null, too short -----------------------------


def test_a_planted_true_forecast_held_up_in_backtest() -> None:
    proofs, summary = _run(_series("true", 96, 2), _config())
    proof = proofs[0]
    assert proof.verdict is Verdict.PASS and proof.gate_outcome is GateOutcome.SUPPORTED
    assert proof.permutation_scheme is PermutationScheme.BLOCK_SIGN_FLIP
    assert proof.effect_metric is not None and proof.effect_metric.value == "mase_reduction"
    assert proof.effect_interval is not None
    assert [a.attack_id for a in proof.attacks] == ["F1", "F2", "F3", "F4", "F5", "F6"]
    assert proof.forecast is not None and proof.forecast.error_reduction > 0.1
    assert proof.spec_hash is not None and summary.n_tested == 1
    text = rejection_reason(proof)
    assert text.startswith("Held up in backtest")
    assert "does not guarantee the next periods" in text
    assert "proven" not in text.lower() and "will be" not in text.lower()


def test_a_planted_null_is_not_held_up() -> None:
    # a seasonal random walk: the seasonal-naive forecast is the best there is
    verdicts = []
    for seed in range(6):
        proofs, _ = _run(_series("null", 96, seed), _config())
        verdicts.append(proofs[0].verdict)
        assert proofs[0].gate_outcome is not GateOutcome.SUPPORTED
    assert all(v is Verdict.REJECT for v in verdicts)


def test_a_short_series_is_not_testable_with_a_plain_reason() -> None:
    proofs, summary = _run(_series("true", 36, 3), _config())
    proof = proofs[0]
    assert proof.gate_outcome is GateOutcome.NOT_TESTABLE and proof.verdict is Verdict.REJECT
    assert "too few backtest origins" in (proof.failure_reason or "")
    assert summary.n_tested == 0 and proof.p_value is None


def test_no_split_or_a_split_not_by_time_is_not_testable() -> None:
    config = _config()
    frame = _series("true", 96, 4)
    proofs = verify_batch([_candidate()], frame, config, structure=STRUCTURE)
    assert proofs[0].gate_outcome is GateOutcome.NOT_TESTABLE
    assert "held back" in (proofs[0].failure_reason or "")


def test_a_forecast_enters_the_same_bh_family_as_other_claims() -> None:
    config = _config()
    frame = _series("true", 96, 5)
    frame["cost"] = frame["revenue"] * 0.6 + np.random.default_rng(1).normal(0, 3, len(frame))
    trend = CandidateInsight(
        insight_id="tr",
        claim="revenue is positively associated with month",
        claim_type=ClaimType.TREND,
        variables=["month", "revenue"],
        dataset_ref="x",
        asserted_direction=Direction.POSITIVE,
    )
    proofs, summary = _run(frame, config, [_candidate(), trend])
    assert len({p.bh_family_id for p in proofs}) == 1
    assert summary.n_tested + summary.n_screened_out == 2
    tested = [p for p in proofs if p.q_value is not None]
    assert all(p.n_hypotheses_in_batch == len(tested) for p in tested)


def test_an_old_stored_proof_without_a_forecast_field_still_loads() -> None:
    proofs, _ = _run(_series("true", 96, 2), _config())
    payload = proofs[0].model_dump(mode="json")
    payload.pop("forecast")
    assert ProofObject.model_validate(payload).forecast is None
    old = CandidateInsight(
        insight_id="o", claim="a", claim_type=ClaimType.TREND, variables=["a", "b"], dataset_ref="x"
    )
    assert old.forecast is None


# --- the attacks on planted backtests ------------------------------------------------


def _backtest(model_errors: np.ndarray, base_errors: np.ndarray) -> Backtest:
    """A backtest whose absolute errors are exactly the arrays given (scale 1, actual 0)."""
    n, horizon = model_errors.shape
    return Backtest(
        method="trend_seasonal",
        baseline_kind="seasonal_naive",
        season=12,
        horizon=horizon,
        origins=np.arange(30, 30 + n),
        scale=np.ones(n),
        actual=np.zeros((n, horizon)),
        model=-model_errors,
        baseline=-base_errors,
    )


def _attacks(test: Backtest, **overrides):
    config = load_pinned_config()
    settings = config.forecast
    if overrides:
        settings = settings.model_copy(
            update={"attacks": settings.attacks.model_copy(update=overrides)}
        )
    return {a.attack_id: a for a in run_forecast_attacks(test, config.attacks, settings)}


def _noisy(n: int, level: float, horizon: int = 2, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return level * rng.uniform(0.7, 1.3, (n, horizon))


def test_a_clean_better_forecast_survives_every_attack() -> None:
    results = _attacks(_backtest(_noisy(30, 0.4, seed=1), _noisy(30, 1.0, seed=2)))
    assert all(r.outcome is AttackOutcome.SURVIVED for r in results.values())


def test_f3_catches_a_method_good_one_period_ahead_and_bad_two_ahead() -> None:
    base = _noisy(30, 1.0, seed=2)
    model = _noisy(30, 0.2, seed=1)
    model[:, 1] = _noisy(30, 1.5, 1, seed=3)[:, 0]  # worse than the baseline at h = 2
    test = _backtest(model, base)
    assert test.model_loss.sum() < test.baseline_loss.sum()  # still better overall
    f3 = _attacks(test)["F3"]
    assert f3.outcome is AttackOutcome.BROKEN and f3.details["worst_horizon"] == 2


def test_f3_does_not_apply_to_a_one_period_horizon() -> None:
    f3 = _attacks(_backtest(_noisy(30, 0.4, 1, 1), _noisy(30, 1.0, 1, 2)))["F3"]
    assert f3.outcome is AttackOutcome.NOT_RUN and f3.applicable is False


def test_f2_catches_a_method_that_worked_long_ago() -> None:
    base = _noisy(30, 1.0, seed=2)
    model = _noisy(30, 0.2, seed=1)
    model[20:] = base[20:] * 1.4  # worse than the baseline on the most recent third
    test = _backtest(model, base)
    assert test.model_loss.sum() < test.baseline_loss.sum()
    assert _attacks(test)["F2"].outcome is AttackOutcome.BROKEN


def test_f1_catches_an_advantage_that_lives_in_a_few_origins() -> None:
    base = np.ones((30, 2))
    model = base * 1.05
    model[:3] = 0.0  # three origins carry the whole advantage
    test = _backtest(model, base)
    assert test.model_loss.sum() < test.baseline_loss.sum()
    assert _attacks(test)["F1"].outcome is AttackOutcome.BROKEN


def test_f6_catches_an_advantage_made_by_one_outlying_baseline_month() -> None:
    base = _noisy(30, 1.0, seed=2)
    model = base * 1.03
    base[7] = 40.0  # last year's same month was an outlier the baseline copied
    test = _backtest(model, base)
    assert test.model_loss.sum() < test.baseline_loss.sum()
    assert _attacks(test)["F6"].outcome is AttackOutcome.BROKEN


def test_f5_finds_a_break_and_breaks_the_claim_when_the_advantage_vanishes_after_it() -> None:
    base = _noisy(40, 1.0, seed=2)
    model = _noisy(40, 0.2, seed=1)
    model[24:] = base[24:] * 1.2  # the method's errors jump at origin 24 and stay up
    test = _backtest(model, base)
    assert test.model_loss.sum() < test.baseline_loss.sum()
    f5 = _attacks(test)["F5"]
    assert f5.outcome is AttackOutcome.BROKEN
    assert "A break is not proof the forecast is bad" in f5.reason


def test_f5_leaves_a_stable_method_alone() -> None:
    f5 = _attacks(_backtest(_noisy(40, 0.4, seed=1), _noisy(40, 1.0, seed=2)))["F5"]
    assert f5.outcome is AttackOutcome.SURVIVED and "no structural break" in f5.reason


def test_f4_is_wording_only_unless_the_config_says_otherwise() -> None:
    base = _noisy(40, 1.0, seed=2)
    model = _noisy(40, 0.3, seed=1)
    model[20:] *= 6.0  # later errors far larger than the range built on the earlier ones
    test = _backtest(model, base)
    soft = _attacks(test)["F4"]
    assert soft.outcome is AttackOutcome.SURVIVED and soft.details["calibrated"] is False
    assert "not calibrated" in soft.reason
    hard = _attacks(test, calibration_changes_verdict=True)["F4"]
    assert hard.outcome is AttackOutcome.BROKEN


def test_attacks_never_turn_a_reject_into_a_pass() -> None:
    # a null forecast is REJECT before any attack; the ratchet only runs on a PASS
    proofs, _ = _run(_series("null", 96, 11), _config())
    assert proofs[0].verdict is Verdict.REJECT and proofs[0].attacks == []
