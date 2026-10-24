"""The gateway on time-ordered and grouped tables (PLAN D5, D6, D6b; P1).

Each claim must be tested under a null that matches how its rows depend on each other,
refused when no valid null exists, and refused when a program built a different null
from the one the gate assigned.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.contracts.enums import ClaimType, Direction, GateOutcome, PermutationScheme, Verdict
from pramana.contracts.structure import DataStructure
from pramana.verification.config import VerificationConfig
from pramana.verification.falsification.generator import generate_from_template
from pramana.verification.gateway import verify_batch, verify_batch_with_summary
from pramana.verification.schemes import (
    PERIOD_COLUMN,
    confirmation_frame,
    exploration_frame,
    split_rows,
    with_period_column,
)
from tests.fixtures.candidates import candidate
from tests.fixtures.config import load_pinned_config


@pytest.fixture(scope="module")
def config() -> VerificationConfig:
    shipped = load_pinned_config()
    return shipped.model_copy(
        update={"statistics": shipped.statistics.model_copy(update={"n_permutations": 999})}
    )


def _series(n: int, drift: float, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = pd.date_range("2020-01-01", periods=n, freq="MS")
    return pd.DataFrame(
        {
            "month": months,
            "revenue": 100 + np.cumsum(drift + rng.normal(size=n)),
            "cost": 50 + np.cumsum(rng.normal(size=n)),
        }
    )


SERIES = DataStructure(
    shape="time_series", time_column="month", period="month", declared_by="shape_classifier"
)


def _trend(insight_id: str = "t1"):
    return candidate(
        insight_id,
        "revenue tends to rise over the months in this data",
        ClaimType.TREND,
        ["month", "revenue"],
        direction=Direction.POSITIVE,
    )


def _panel(entities: int = 10, periods: int = 24, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for e in range(entities):
        tier = "large" if e % 2 else "small"
        level = rng.normal()
        for p in range(periods):
            rows.append(
                {
                    "year": 2000 + p,
                    "region": f"r{e}",
                    "tier": tier,
                    "sales": level + 0.1 * p + rng.normal(),
                    "ads": 0.1 * p + rng.normal(),
                    "promo": "yes" if (e + p) % 2 else "no",
                }
            )
    return pd.DataFrame(rows)


PANEL = DataStructure(
    shape="panel",
    time_column="year",
    entity_column="region",
    period="year",
    declared_by="shape_classifier",
)


def test_a_trend_on_a_series_is_tested_on_differences_and_finds_a_drift(config) -> None:
    proof = verify_batch([_trend()], _series(60, drift=1.0), config, structure=SERIES)[0]
    assert proof.permutation_scheme is PermutationScheme.BLOCK_DIFFERENCED
    assert proof.verdict is Verdict.PASS
    assert "BLOCK_LENGTH" in (proof.falsification_code or "")


def test_twelve_months_are_too_few_periods_to_test(config) -> None:
    proof = verify_batch([_trend()], _series(12, drift=1.0), config, structure=SERIES)[0]
    assert proof.gate_outcome is GateOutcome.NOT_TESTABLE
    assert "too few periods" in (proof.failure_reason or "")


def test_differences_that_still_wander_are_refused(config) -> None:
    frame = _series(60, drift=0.0)
    frame["revenue"] = np.cumsum(np.cumsum(np.random.default_rng(4).normal(size=60)))
    proof = verify_batch([_trend()], frame, config, structure=SERIES)[0]
    assert proof.gate_outcome is GateOutcome.NOT_TESTABLE
    assert "still strongly dependent" in (proof.failure_reason or "")


def test_a_group_comparison_on_a_series_has_no_valid_null(config) -> None:
    frame = _series(60, drift=0.0)
    frame["half"] = ["a", "b"] * 30
    claim = candidate(
        "g1",
        "revenue differs between halves in this data",
        ClaimType.GROUP_DIFFERENCE,
        ["half", "revenue"],
    )
    proof = verify_batch([claim], frame, config, structure=SERIES)[0]
    assert proof.gate_outcome is GateOutcome.NOT_TESTABLE


def test_panel_claims_get_stratified_and_cluster_nulls(config) -> None:
    claims = [
        candidate(
            "c1",
            "sales tend to move with ads in this data",
            ClaimType.CORRELATION,
            ["ads", "sales"],
        ),
        candidate(
            "g1", "sales differ by tier in this data", ClaimType.GROUP_DIFFERENCE, ["tier", "sales"]
        ),
        candidate(
            "g2",
            "sales differ with promo in this data",
            ClaimType.GROUP_DIFFERENCE,
            ["promo", "sales"],
        ),
        candidate(
            "g3",
            "sales differ by region in this data",
            ClaimType.GROUP_DIFFERENCE,
            ["region", "sales"],
        ),
    ]
    proofs = {p.insight_id: p for p in verify_batch(claims, _panel(), config, structure=PANEL)}
    assert proofs["c1"].permutation_scheme is PermutationScheme.STRATIFIED
    assert proofs["g1"].permutation_scheme is PermutationScheme.CLUSTER
    assert proofs["g2"].permutation_scheme is PermutationScheme.STRATIFIED
    assert proofs["g3"].gate_outcome is GateOutcome.NOT_TESTABLE
    # ads and sales only share a time trend: within years they are unrelated
    assert proofs["c1"].verdict is Verdict.REJECT
    for key in ("c1", "g1", "g2"):
        assert proofs[key].gate_outcome is not GateOutcome.NOT_TESTABLE, proofs[key]
        assert proofs[key].n_hypotheses_in_batch == 3


def test_a_program_that_builds_the_wrong_null_is_refused(config) -> None:
    def free_test_labelled_as_assigned(candidate_, config_, plan=None):
        program = generate_from_template(candidate_, config_)  # a free shuffle
        return program.model_copy(update={"scheme": plan.scheme, "structure_columns": plan.columns})

    proof = verify_batch(
        [_trend()],
        _series(60, drift=1.0),
        config,
        structure=SERIES,
        generate=free_test_labelled_as_assigned,
    )[0]
    assert proof.gate_outcome is GateOutcome.INCONCLUSIVE
    assert "block_differenced" in (proof.failure_reason or "")


def test_a_two_argument_generator_cannot_serve_time_ordered_rows(config) -> None:
    proof = verify_batch(
        [_trend()],
        _series(60, drift=1.0),
        config,
        structure=SERIES,
        generate=lambda c, cfg: generate_from_template(c, cfg),
    )[0]
    assert proof.verdict is Verdict.REJECT
    assert proof.gate_outcome is GateOutcome.NOT_TESTABLE


def test_without_a_structure_rows_are_declared_independent(config) -> None:
    frame = pd.DataFrame({"x": np.arange(40.0), "y": np.arange(40.0) * 2})
    claim = candidate(
        "c1", "y tends to rise with x in this data", ClaimType.CORRELATION, ["x", "y"]
    )
    proofs, summary = verify_batch_with_summary([claim], frame, config)
    assert proofs[0].permutation_scheme is PermutationScheme.FREE
    assert summary.structure is not None and summary.structure.declared_by == "caller"


def test_a_family_larger_than_m_max_is_refused(config) -> None:
    claims = [_trend(f"t{i}") for i in range(config.statistics.m_max + 1)]
    with pytest.raises(ValueError, match="m_max"):
        verify_batch(claims, _series(60, 1.0), config, structure=SERIES)


# --- the split (D5) -----------------------------------------------------------


def test_a_series_confirms_on_its_later_half(config) -> None:
    frame = _series(40, drift=0.0)
    explore, confirm, record = split_rows(frame, SERIES, config)
    assert record.method == "by_time"
    assert set(explore).isdisjoint(confirm) and len(explore) + len(confirm) == 40
    assert frame["month"].iloc[confirm].min() > frame["month"].iloc[explore].max()


def test_a_panel_with_enough_entities_splits_whole_entities(config) -> None:
    frame = _panel(entities=10)
    explored, record = exploration_frame(frame, PANEL, config)
    confirmed, again = confirmation_frame(frame, PANEL, config)
    assert record == again and record.method == "by_entity"
    assert set(explored["region"]).isdisjoint(confirmed["region"])
    assert len(explored) + len(confirmed) == len(frame)


def test_independent_rows_split_at_random_and_reproducibly(config) -> None:
    frame = pd.DataFrame({"x": np.arange(101.0)})
    structure = DataStructure.independent_rows()
    first = split_rows(frame, structure, config)
    second = split_rows(frame, structure, config)
    assert first[2] == second[2] and first[2].method == "random_rows"
    assert first[2].n_confirmation == 50 or first[2].n_confirmation == 51


def test_the_period_column_is_one_value_per_month(config) -> None:
    frame = pd.DataFrame({"month": ["2024-01-03", "2024-01-20", "2024-02-01"], "v": [1, 2, 3]})
    structure = DataStructure(
        shape="transactions", time_column="month", period="month", declared_by="shape_classifier"
    )
    periods = with_period_column(frame, structure)[PERIOD_COLUMN]
    assert periods.iloc[0] == periods.iloc[1] < periods.iloc[2]
