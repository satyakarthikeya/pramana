"""Inputs the gate must refuse rather than decide on: NaN statistics and untested directions."""

from __future__ import annotations

import numpy as np
import pytest

from pramana.contracts.enums import Direction, EffectMetric
from pramana.verification.attacks.runner import _same_level
from pramana.verification.config import load_config
from pramana.verification.evidence import evaluate_gate
from pramana.verification.stats.permutation import _p_value


def _gate(**overrides: object):
    config = load_config()
    arguments = {
        "q_value": 0.001,
        "effect_size": 0.4,
        "effect_metric": EffectMetric.SPEARMAN_RHO,
        "alpha": config.statistics.alpha,
        "p_value_floor": config.p_value_floor,
        "config": config.evidence,
    }
    return evaluate_gate(**{**arguments, **overrides})


def test_a_nan_q_value_is_refused_not_passed() -> None:
    with pytest.raises(ValueError, match="not a probability"):
        _gate(q_value=float("nan"))


def test_a_direction_on_an_unsigned_metric_is_refused() -> None:
    with pytest.raises(ValueError, match="has no sign"):
        _gate(effect_metric=EffectMetric.EPSILON_SQUARED, asserted_direction=Direction.POSITIVE)


def test_a_nan_statistic_never_gets_the_smallest_p_value() -> None:
    null = np.zeros(99)
    with pytest.raises(ValueError, match="not finite"):
        _p_value(float("nan"), null, "two-sided")
    with pytest.raises(ValueError, match="not finite"):
        _p_value(0.5, np.append(null, np.nan), "two-sided")


def test_group_levels_written_differently_are_the_same_level() -> None:
    assert _same_level("1.0", "1") and _same_level(" Male", "male")
    assert not _same_level("2", "1")
