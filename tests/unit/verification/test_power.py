"""S1: the smallest effect the rows could have found (known answers) and the note on a REJECT."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from pramana.contracts import ClaimType, Direction, EffectMetric, GateOutcome, PermutationScheme
from pramana.verification.gateway import verify_batch
from pramana.verification.power import detectable_effect, power_note
from tests.fixtures.candidates import candidate
from tests.fixtures.config import load_pinned_config


def test_rank_correlation_known_answer() -> None:
    # n = 100, alpha 0.05, power 0.8: Fisher z, (1.96 + 0.8416) / sqrt(97) = 0.2845
    r = detectable_effect(EffectMetric.SPEARMAN_RHO, 100, 0.05, 0.8)
    assert r == pytest.approx(math.tanh(2.8016 * math.sqrt(1.06 / 97)), abs=1e-3)
    assert 0.27 < r < 0.31


def test_more_data_detects_smaller_effects() -> None:
    sizes = [20, 50, 200, 1000]
    found = [detectable_effect(EffectMetric.SPEARMAN_RHO, n, 0.05, 0.8) for n in sizes]
    assert found == sorted(found, reverse=True)


def test_group_difference_noncentral_f_is_in_range_and_shrinks_with_n() -> None:
    small = detectable_effect(EffectMetric.EPSILON_SQUARED, 40, 0.05, 0.8, groups=3)
    large = detectable_effect(EffectMetric.EPSILON_SQUARED, 400, 0.05, 0.8, groups=3)
    assert 0 < large < small < 1
    # Cohen: f2 = 0.0625 gives power 0.8 near n = 160 for 3 groups -> eta2 ~ 0.06
    mid = detectable_effect(EffectMetric.EPSILON_SQUARED, 160, 0.05, 0.8, groups=3)
    assert 0.04 < mid < 0.09


def test_no_note_for_tiny_samples_or_unsupported_metrics() -> None:
    assert detectable_effect(EffectMetric.SPEARMAN_RHO, 5, 0.05, 0.8) is None
    assert detectable_effect(EffectMetric.RELATIVE_CHANGE, 100, 0.05, 0.8) is None


def test_effective_sample_follows_the_scheme() -> None:
    kwargs = dict(n_observations=200, n_periods=20, n_entities=8, groups=None, alpha=0.05, power=0.8)
    free = power_note(EffectMetric.SPEARMAN_RHO, PermutationScheme.FREE, **kwargs)
    strat = power_note(EffectMetric.SPEARMAN_RHO, PermutationScheme.STRATIFIED, **kwargs)
    cluster = power_note(EffectMetric.SPEARMAN_RHO, PermutationScheme.CLUSTER, **kwargs)
    assert (free.n_effective, strat.n_effective, cluster.n_effective) == (200, 180, 8)
    assert cluster.unit == "entities" and cluster.detectable_effect > strat.detectable_effect


def test_a_non_significant_claim_carries_a_note_and_a_significant_one_does_not() -> None:
    rng = np.random.default_rng(5)
    n = 60
    x = rng.normal(size=n)
    frame = pd.DataFrame({"x": x, "noise": rng.normal(size=n), "y": x + rng.normal(0, 0.5, n)})
    claims = [
        candidate(
            f"c{i}",
            f"{b} is positively associated with {a}",
            ClaimType.CORRELATION,
            [a, b],
            direction=Direction.POSITIVE,
        )
        for i, (a, b) in enumerate([("x", "noise"), ("x", "y")])
    ]
    proofs = {p.insight_id: p for p in verify_batch(claims, frame, load_pinned_config())}
    assert proofs["c0"].gate_outcome is GateOutcome.INCONCLUSIVE
    assert proofs["c0"].power is not None and proofs["c0"].power.n_effective == n
    assert proofs["c1"].power is None  # significant claims get no note
