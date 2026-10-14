"""The planted-dataset builder: reproducible, independent shuffle, calibrated injection."""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
import pytest

from pramana.contracts.enums import EffectMetric
from pramana.evaluation.config import EvaluationConfig, RelationshipType
from pramana.evaluation.planted import (
    build_planted_dataset,
    dataset_seed,
    k_for,
    scheduled_injections,
)
from pramana.verification.config import VerificationConfig
from pramana.verification.stats import spearman_rho


def _build(extract, eval_config, ver_config, *, index=0, k=None):
    frame, ordinal = extract
    return build_planted_dataset(
        frame,
        dataset_id=f"ds-{index}",
        dataset_index=index,
        config=eval_config,
        verification=ver_config,
        ordinal_columns=ordinal,
        k=k,
    )


def test_same_seed_gives_identical_frame_and_truth(extract, eval_config, ver_config) -> None:
    first = _build(extract, eval_config, ver_config, index=0)
    second = _build(extract, eval_config, ver_config, index=0)
    pd.testing.assert_frame_equal(first.frame, second.frame)
    assert first.truth.model_dump_json() == second.truth.model_dump_json()
    assert first.truth.frame_digest == second.truth.frame_digest


def test_different_dataset_index_gives_a_different_build(extract, eval_config, ver_config) -> None:
    first = _build(extract, eval_config, ver_config, index=0)
    second = _build(extract, eval_config, ver_config, index=1)
    assert first.truth.build_seed != second.truth.build_seed
    assert first.truth.frame_digest != second.truth.frame_digest


def test_build_seed_and_schedule_are_recorded(extract, eval_config, ver_config) -> None:
    built = _build(extract, eval_config, ver_config, index=0)
    assert built.truth.build_seed == dataset_seed(eval_config.planted, 0)
    assert built.truth.k == k_for(eval_config.planted, 0)
    assert len(built.truth.schedule) == built.truth.k
    assert built.truth.base_seed == eval_config.planted.base_seed


def test_independent_shuffle_destroys_a_real_correlation(eval_config, ver_config) -> None:
    rng = np.random.default_rng(0)
    n = 1500
    x = rng.normal(size=n)
    real = pd.DataFrame(
        {"a": x, "b": x + rng.normal(scale=0.3, size=n), "t": np.arange(n) % 12}
    )
    assert spearman_rho(real["a"], real["b"]) > 0.9  # the real association exists

    built = build_planted_dataset(
        real,
        dataset_id="real",
        dataset_index=0,
        config=eval_config,
        verification=ver_config,
        ordinal_columns=["t"],
        k=0,
    )
    assert abs(spearman_rho(built.frame["a"], built.frame["b"])) < 0.1
    # Marginals untouched: shuffling only moves values.
    for column in real.columns:
        assert sorted(built.frame[column]) == sorted(real[column])


def test_k_zero_labels_every_pair_null(extract, eval_config, ver_config) -> None:
    built = _build(extract, eval_config, ver_config, index=3, k=0)
    assert built.truth.k == 0
    assert {row.label for row in built.truth.rows} == {"null"}


def test_every_pair_is_labelled_exactly_once(extract, eval_config, ver_config) -> None:
    built = _build(extract, eval_config, ver_config, index=0)
    columns = list(built.frame.columns)
    expected = {frozenset(pair) for pair in combinations(columns, 2)}
    labelled = [frozenset((row.var_a, row.var_b)) for row in built.truth.rows]
    assert len(labelled) == len(set(labelled))
    assert set(labelled) == expected
    injected = [row for row in built.truth.rows if row.label == "injected"]
    assert len(injected) == k_for(eval_config.planted, 0)


def test_injections_use_disjoint_columns(extract, eval_config, ver_config) -> None:
    """Sharing a column would make pairs between injections non-null and mislabel them."""
    built = _build(extract, eval_config, ver_config, index=0, k=3)
    used = [
        c for row in built.truth.rows if row.label == "injected" for c in (row.var_a, row.var_b)
    ]
    assert len(used) == len(set(used))


def test_realised_effect_hits_target_with_the_right_sign(
    extract, eval_config: EvaluationConfig, ver_config
) -> None:
    built = _build(extract, eval_config, ver_config, index=0, k=3)
    tolerance = eval_config.planted.calibration_tolerance
    seen_types = set()
    for row in built.truth.rows:
        if row.label != "injected":
            continue
        seen_types.add(row.relationship_type)
        assert row.realised_effect is not None and row.target_effect is not None
        assert abs(abs(row.realised_effect) - row.target_effect) <= tolerance
        assert (row.realised_effect > 0) == (row.direction.value == "positive")
    assert seen_types == {
        RelationshipType.MONOTONIC,
        RelationshipType.SHIFT,
        RelationshipType.TREND,
    }


def test_schedule_straddles_the_gate_floor(extract, eval_config, ver_config) -> None:
    """Targets are multiples of the verification floor; some above, some below it."""
    rows = []
    for index in range(4):
        rows += [
            r for r in _build(extract, eval_config, ver_config, index=index).truth.rows
            if r.label == "injected"
        ]
    assert any(r.target_effect >= r.floor for r in rows)
    assert any(r.target_effect < r.floor for r in rows)
    for r in rows:
        assert r.target_effect == pytest.approx(r.multiplier_of_floor * r.floor)
        band = ver_config.evidence.threshold_for(r.effect_metric)
        assert r.floor == band.min


def test_targets_follow_the_verification_floors(
    extract, eval_config, ver_config: VerificationConfig
) -> None:
    """Recalibrating the bands moves the targets; no number is copied into the schedule."""
    thresholds = {
        metric: band.model_copy(update={"min": band.min * 0.5, "strong": band.strong})
        for metric, band in ver_config.evidence.effect_thresholds.items()
    }
    halved = ver_config.model_copy(
        update={
            "evidence": ver_config.evidence.model_copy(update={"effect_thresholds": thresholds})
        }
    )
    base = _build(extract, eval_config, ver_config, index=0, k=3)
    moved = _build(extract, eval_config, halved, index=0, k=3)
    for a, b in zip(
        (r for r in base.truth.rows if r.label == "injected"),
        (r for r in moved.truth.rows if r.label == "injected"),
        strict=True,
    ):
        assert b.floor == pytest.approx(a.floor * 0.5)
        assert b.target_effect == pytest.approx(a.target_effect * 0.5)


def test_group_labels_are_recorded_in_the_template_string_form(
    extract, eval_config, ver_config
) -> None:
    built = _build(extract, eval_config, ver_config, index=0, k=3)
    shift = next(r for r in built.truth.rows if r.relationship_type is RelationshipType.SHIFT)
    assert shift.levels == sorted(shift.levels)
    assert shift.reference_group == shift.levels[0]
    assert shift.effect_metric is EffectMetric.CLIFFS_DELTA


def test_scheduled_injections_cycle_deterministically(eval_config) -> None:
    first = scheduled_injections(eval_config.planted, 0, 3)
    assert first == scheduled_injections(eval_config.planted, 0, 3)
    assert [s.relationship_type for s in first] == list(eval_config.planted.relationship_cycle)[:3]
