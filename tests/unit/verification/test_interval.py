"""S5: the interval beside an effect resamples the unit the null shuffles."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from pramana.contracts import ClaimType, Direction, PermutationScheme, ProofObject
from pramana.verification.attacks import ClaimView
from pramana.verification.gateway import verify_batch
from pramana.verification.interval import effect_interval
from pramana.verification.schemes import PERIOD_COLUMN
from tests.fixtures.candidates import candidate
from tests.fixtures.config import load_pinned_config

CLAIM = ClaimView(ClaimType.CORRELATION, "x", "y", PermutationScheme.FREE)


def _pairs(rng: np.random.Generator, n: int = 150) -> pd.DataFrame:
    x = rng.normal(size=n)
    return pd.DataFrame({"x": x, "y": x + rng.normal(size=n)})


def test_interval_covers_the_true_rank_correlation_about_as_often_as_promised() -> None:
    truth = 6 / math.pi * math.asin(1 / math.sqrt(2) / 2)  # y = x + N(0,1): r = 0.707
    rng = np.random.default_rng(11)
    covered = 0
    sims = 40
    for i in range(sims):
        found = effect_interval(CLAIM, _pairs(rng), n_resamples=400, confidence=0.95, seed=i)
        assert found is not None and found.method == "row_bootstrap"
        covered += found.low <= truth <= found.high
    assert covered / sims >= 0.8  # nominal 0.95; loose for 40 simulations


def test_same_seed_same_interval() -> None:
    rows = _pairs(np.random.default_rng(2))
    a = effect_interval(CLAIM, rows, n_resamples=300, confidence=0.9, seed=5)
    b = effect_interval(CLAIM, rows, n_resamples=300, confidence=0.9, seed=5)
    assert a == b


def test_resampling_whole_entities_is_wider_when_entities_share_a_level() -> None:
    rng = np.random.default_rng(3)
    frames = []
    for entity in range(10):
        shift = rng.normal(scale=3.0)
        x = rng.normal(size=12) + shift
        frames.append(pd.DataFrame({"entity": f"e{entity}", "x": x, "y": x + rng.normal(size=12)}))
    rows = pd.concat(frames, ignore_index=True)
    rows_view = ClaimView(ClaimType.CORRELATION, "x", "y", PermutationScheme.FREE)
    entity_view = ClaimView(
        ClaimType.CORRELATION, "x", "y", PermutationScheme.CLUSTER, entity_column="entity"
    )
    by_row = effect_interval(rows_view, rows, n_resamples=400, confidence=0.95, seed=1)
    by_entity = effect_interval(entity_view, rows, n_resamples=400, confidence=0.95, seed=1)
    assert by_entity is not None and by_entity.method == "entity_bootstrap"
    assert (by_entity.high - by_entity.low) > (by_row.high - by_row.low)


def test_a_block_differenced_series_has_no_interval_yet() -> None:
    view = ClaimView(ClaimType.TREND, "x", "y", PermutationScheme.BLOCK_DIFFERENCED)
    rows = pd.DataFrame({"x": np.arange(30.0), "y": np.arange(30.0), PERIOD_COLUMN: np.arange(30)})
    assert effect_interval(view, rows, n_resamples=100, confidence=0.95, seed=1) is None


def test_a_passing_claim_carries_an_interval_and_a_rejected_one_does_not() -> None:
    rng = np.random.default_rng(6)
    frame = _pairs(rng, 120).assign(noise=rng.normal(size=120))
    claims = [
        candidate(
            "t",
            "y is positively associated with x",
            ClaimType.CORRELATION,
            ["x", "y"],
            direction=Direction.POSITIVE,
        ),
        candidate(
            "f",
            "noise is positively associated with x",
            ClaimType.CORRELATION,
            ["x", "noise"],
            direction=Direction.POSITIVE,
        ),
    ]
    proofs = {p.insight_id: p for p in verify_batch(claims, frame, load_pinned_config())}
    assert proofs["t"].effect_interval is not None and proofs["t"].effect_interval.low > 0.4
    assert proofs["f"].effect_interval is None


def test_a_proof_stored_before_these_fields_still_loads() -> None:
    old = {
        "insight_id": "x",
        "verdict": "REJECT",
        "gate_outcome": "not_testable",
        "bh_family_id": "fam",
        "seed": 1,
        "failure_reason": "too few rows",
    }
    proof = ProofObject.model_validate(old)
    assert proof.effect_interval is None and proof.power is None
