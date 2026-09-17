"""Gate and evidence-score tests (SCOPE.md 4 step 4).

The gate decides; the score only ranks. These tests pin that separation, because
collapsing the two would silently forfeit the FDR guarantee.
"""

from __future__ import annotations

import pytest

from pramana.contracts.enums import Direction, EffectMetric, GateOutcome, Verdict
from pramana.verification.config import VerificationConfig, load_config
from pramana.verification.evidence import (
    effect_leg,
    evaluate_gate,
    evidence_score,
    significance_leg,
)

ALPHA = 0.05


@pytest.fixture(scope="module")
def config() -> VerificationConfig:
    return load_config()


def _gate(config: VerificationConfig, **overrides: object) -> object:
    kwargs: dict[str, object] = {
        "q_value": 0.001,
        "effect_size": 0.4,
        "effect_metric": EffectMetric.SPEARMAN_RHO,
        "alpha": config.statistics.alpha,
        "p_value_floor": config.p_value_floor,
        "config": config.evidence,
    }
    kwargs.update(overrides)
    return evaluate_gate(**kwargs)  # type: ignore[arg-type]


# --- the four outcomes ----------------------------------------------------


def test_strong_directed_claim_is_supported(config: VerificationConfig) -> None:
    decision = _gate(config, asserted_direction=Direction.POSITIVE)
    assert decision.outcome is GateOutcome.SUPPORTED
    assert decision.verdict is Verdict.PASS
    assert decision.evidence_score is not None


def test_significant_but_wrong_direction_is_refuted(config: VerificationConfig) -> None:
    """The claim says "rises with"; the data says it falls, strongly. That is not
    an inconclusive result -- the data refutes the claim as stated."""
    decision = _gate(config, effect_size=-0.4, asserted_direction=Direction.POSITIVE)
    assert decision.outcome is GateOutcome.REFUTED
    assert decision.verdict is Verdict.REJECT
    assert decision.evidence_score is None


def test_significant_but_tiny_effect_is_negligible(config: VerificationConfig) -> None:
    decision = _gate(config, effect_size=0.04)
    assert decision.outcome is GateOutcome.NEGLIGIBLE
    assert decision.verdict is Verdict.REJECT
    assert decision.evidence_score is None


def test_non_significant_is_inconclusive(config: VerificationConfig) -> None:
    decision = _gate(config, q_value=0.20, effect_size=0.9)
    assert decision.outcome is GateOutcome.INCONCLUSIVE
    assert decision.verdict is Verdict.REJECT
    assert decision.evidence_score is None


def test_q_exactly_at_alpha_is_inconclusive(config: VerificationConfig) -> None:
    """The rejection rule is strict: q < alpha, not q <= alpha."""
    decision = _gate(config, q_value=config.statistics.alpha)
    assert decision.outcome is GateOutcome.INCONCLUSIVE


def test_effect_exactly_at_min_is_supported(config: VerificationConfig) -> None:
    """The threshold is inclusive: |e| >= min_effect."""
    band = config.evidence.threshold_for(EffectMetric.SPEARMAN_RHO)
    decision = _gate(config, effect_size=band.min)
    assert decision.outcome is GateOutcome.SUPPORTED
    assert decision.evidence_score == pytest.approx(0.0)  # s_e is exactly 0 here


def test_undirected_claim_skips_the_direction_check(config: VerificationConfig) -> None:
    decision = _gate(config, effect_size=-0.4, asserted_direction=None)
    assert decision.outcome is GateOutcome.SUPPORTED


# --- verdict/outcome invariant -------------------------------------------


@pytest.mark.parametrize(
    ("q", "effect", "direction"),
    [
        (0.001, 0.4, Direction.POSITIVE),
        (0.001, -0.4, Direction.POSITIVE),
        (0.001, 0.02, None),
        (0.9, 0.8, None),
    ],
)
def test_pass_iff_supported(
    config: VerificationConfig, q: float, effect: float, direction: Direction | None
) -> None:
    decision = _gate(config, q_value=q, effect_size=effect, asserted_direction=direction)
    assert (decision.verdict is Verdict.PASS) == (decision.outcome is GateOutcome.SUPPORTED)
    assert (decision.evidence_score is not None) == (decision.outcome is GateOutcome.SUPPORTED)


# --- metric-specific behaviour -------------------------------------------


def test_epsilon_squared_is_gated_on_its_square_root(config: VerificationConfig) -> None:
    """eps^2 = 0.02 -> sqrt = 0.141, which clears the 0.10 floor. Gating on the raw
    ratio would have wrongly called this negligible."""
    decision = _gate(config, effect_size=0.02, effect_metric=EffectMetric.EPSILON_SQUARED)
    assert decision.outcome is GateOutcome.SUPPORTED


def test_unsigned_metrics_have_no_observed_direction(config: VerificationConfig) -> None:
    decision = _gate(config, effect_size=0.3, effect_metric=EffectMetric.EPSILON_SQUARED)
    assert decision.observed_direction is None


def test_cramers_v_threshold_shrinks_with_table_size(config: VerificationConfig) -> None:
    """A fixed cutoff would let large contingency tables pass trivially."""
    small = _gate(config, effect_size=0.09, effect_metric=EffectMetric.CRAMERS_V, table_k=2)
    large = _gate(config, effect_size=0.09, effect_metric=EffectMetric.CRAMERS_V, table_k=5)
    assert small.outcome is GateOutcome.NEGLIGIBLE  # threshold 0.10
    assert large.outcome is GateOutcome.SUPPORTED   # threshold 0.10/2 = 0.05
    assert large.min_effect < small.min_effect


def test_cramers_v_requires_table_size(config: VerificationConfig) -> None:
    with pytest.raises(ValueError, match="k = min"):
        _gate(config, effect_metric=EffectMetric.CRAMERS_V, table_k=None)


def test_trend_threshold_is_lower_than_correlation(config: VerificationConfig) -> None:
    """tau runs smaller than rho for the same relationship, so a single global
    cutoff would silently make trend claims harder to pass."""
    tau_band = config.evidence.threshold_for(EffectMetric.KENDALL_TAU_B)
    rho_band = config.evidence.threshold_for(EffectMetric.SPEARMAN_RHO)
    assert tau_band.min < rho_band.min


# --- the score ------------------------------------------------------------


def test_score_is_geometric_so_the_weakest_leg_caps_it() -> None:
    """A large effect must not buy confidence that a marginal q denies."""
    balanced = evidence_score(0.5, 0.5, 1.0)
    lopsided = evidence_score(0.02, 1.0, 1.0)
    assert lopsided < balanced
    assert evidence_score(0.0, 1.0, 1.0) == 0.0


def test_score_is_monotone_in_each_leg() -> None:
    assert evidence_score(0.3, 0.5, 1.0) < evidence_score(0.6, 0.5, 1.0)
    assert evidence_score(0.5, 0.3, 1.0) < evidence_score(0.5, 0.6, 1.0)
    assert evidence_score(0.5, 0.5, 0.5) < evidence_score(0.5, 0.5, 1.0)


def test_significance_leg_does_not_saturate_immediately() -> None:
    """On a linear scale every strong claim would score 1.0 and stop discriminating."""
    floor = 1.0 / 10001.0
    modest = significance_leg(0.01, ALPHA, floor)
    strong = significance_leg(0.0005, ALPHA, floor)
    assert 0.0 < modest < strong < 1.0


def test_significance_leg_is_zero_at_and_above_alpha() -> None:
    floor = 1.0 / 10001.0
    assert significance_leg(ALPHA, ALPHA, floor) == 0.0
    assert significance_leg(0.5, ALPHA, floor) == 0.0


def test_significance_leg_maxes_at_the_permutation_floor() -> None:
    floor = 1.0 / 10001.0
    assert significance_leg(floor, ALPHA, floor) == pytest.approx(1.0)


def test_effect_leg_clips_at_both_ends() -> None:
    assert effect_leg(0.05, 0.10, 0.50) == 0.0
    assert effect_leg(0.10, 0.10, 0.50) == 0.0
    assert effect_leg(0.30, 0.10, 0.50) == pytest.approx(0.5)
    assert effect_leg(0.90, 0.10, 0.50) == 1.0


def test_score_legs_must_be_normalized() -> None:
    with pytest.raises(ValueError, match="s_q"):
        evidence_score(1.5, 0.5, 1.0)


def test_zero_q_is_refused() -> None:
    """p-values are add-one floored, so a zero q means something upstream is wrong."""
    with pytest.raises(ValueError, match="q_value must be positive"):
        significance_leg(0.0, ALPHA, 1.0 / 10001.0)


# --- non-finite effects fail closed --------------------------------------


@pytest.mark.parametrize("effect", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_effect_cannot_be_supported(config: VerificationConfig, effect: float) -> None:
    """Every comparison against NaN is False, so `gated_effect < band.min` would let a
    NaN past the magnitude check and `effect_leg` would clamp it to a full 1.0 -- a
    false SUPPORTED / PASS. The gate must refuse to decide rather than mis-decide."""
    with pytest.raises(ValueError, match="not a finite number"):
        _gate(config, effect_size=effect)
