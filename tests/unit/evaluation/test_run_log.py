"""The per-run log carries every SPEC.md 5 field, and the metrics recompute from it alone."""

from __future__ import annotations

import json

import pytest

from pramana.evaluation.conditions import Condition, run_condition
from pramana.evaluation.metrics import score_reported
from pramana.evaluation.run_log import (
    SPEC_SECTION_5_FIELDS,
    build_run_log,
    read_run_log,
    score_run_log,
    write_run_log,
)
from tests.unit.evaluation.test_conditions import (
    _dataset,
    null_claims,
    proposers_for,
    true_claims,
)


@pytest.fixture(scope="module")
def runs(extract, eval_config, ver_config):
    dataset = _dataset(extract, eval_config, ver_config, index=0, k=3)
    claims = true_claims(dataset)[:1] + null_claims(dataset, 2)
    out = {}
    for condition in (Condition.A, Condition.D):
        result = run_condition(
            condition, dataset.frame, dataset_id="ds-0",
            proposers=proposers_for(claims, eval_config.conditions.analysis_model),
            verification=ver_config, evaluation=eval_config,
        )
        out[condition] = (dataset, result, build_run_log(dataset.truth, result, ver_config))
    return out


@pytest.mark.parametrize("condition", [Condition.A, Condition.D])
def test_log_has_every_spec_field(runs, condition) -> None:
    payload = json.loads(runs[condition][2].model_dump_json())
    for field in SPEC_SECTION_5_FIELDS:
        assert field in payload, field
    config = payload["gateway_config"]
    for key in ("alpha", "n_permutations", "seed", "effect_thresholds"):
        assert key in config
    assert payload["truth"]["build_seed"] == payload["build_seed"]
    assert payload["condition"] == condition.value


def test_condition_d_log_carries_proofs_and_family(runs) -> None:
    log = runs[Condition.D][2]
    assert log.proofs is not None and len(log.proofs) == len(log.candidates)
    assert log.bh_family_id and all(p["bh_family_id"] == log.bh_family_id for p in log.proofs)
    assert log.generator == "template"


def test_condition_a_log_has_explicit_nulls_for_the_gate_fields(runs) -> None:
    payload = json.loads(runs[Condition.A][2].model_dump_json())
    assert payload["proofs"] is None and payload["bh_family_id"] is None
    assert payload["generator"] is None
    assert len(payload["candidates"]) == 3  # A's reported set must be recomputable


@pytest.mark.parametrize("condition", [Condition.A, Condition.D])
def test_metrics_recompute_from_the_log_alone(runs, tmp_path, condition) -> None:
    dataset, result, log = runs[condition]
    live = score_reported(
        dataset.truth,
        [c for c in result.candidates if c.insight_id in set(result.reported_ids)],
    )
    path = write_run_log(log, tmp_path / f"{condition.value}.json")
    assert score_run_log(read_run_log(path)) == live


def test_log_is_byte_reproducible(runs, tmp_path) -> None:
    log = runs[Condition.D][2]
    first = write_run_log(log, tmp_path / "one.json").read_bytes()
    second = write_run_log(log, tmp_path / "two.json").read_bytes()
    assert first == second
