"""`CandidateInsight` generation (SCOPE_P_Rohith.md 2, component 4; 4 step 4).

The acceptance criterion these tests exist to hold is narrow and hard: every object
this module emits must pass the gateway unpatched. That means the real contract model
(`pramana.contracts.CandidateInsight`), the real variable ordering the falsification
templates unpack, and the real admissibility screen -- so one test here deliberately
imports the gateway's screen. It is the only cross-module import in this folder and it
is here as an interface-contract check: if the screen's vocabulary changes, the
analysis module's claim templates should fail loudly in analysis's own suite rather
than silently start producing NOT_TESTABLE claims in production.

`SCOPE_P_Rohith.md` 6 runs on the shared toy frame: one strong planted relationship,
one pure-noise pair, one group difference. `tests/fixtures/frames.py` builds exactly
that, and the gateway acceptance test uses the same fixture, so both modules are
provably testing the same data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.analysis.config import AnalysisConfig, load_config
from pramana.analysis.hypotheses import correlation, group_difference, trend
from pramana.analysis.hypotheses.base import emit, slug, usable_pair
from pramana.analysis.hypotheses.generation import analyse, generate_candidates
from pramana.analysis.schema_inference import SchemaProfile, infer_schema
from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType, Direction
from pramana.verification.admissibility import screen
from tests.fixtures.frames import toy_frame

DATASET_REF = "toy_frame"


@pytest.fixture
def config() -> AnalysisConfig:
    """The shipped config -- these tests assert against what the project actually runs."""
    return load_config()


@pytest.fixture
def frame() -> pd.DataFrame:
    return toy_frame()


@pytest.fixture
def schema(frame: pd.DataFrame, config: AnalysisConfig) -> SchemaProfile:
    return infer_schema(frame, config.schema_inference)


@pytest.fixture
def candidates(
    frame: pd.DataFrame, schema: SchemaProfile, config: AnalysisConfig
) -> list[CandidateInsight]:
    return generate_candidates(
        frame, schema, config.hypotheses, dataset_ref=DATASET_REF
    )


def _by_variables(
    candidates: list[CandidateInsight], *variables: str
) -> CandidateInsight | None:
    return next((item for item in candidates if item.variables == list(variables)), None)


# --- the acceptance test (SCOPE_P_Rohith.md 6) -----------------------------


def test_every_planted_relationship_is_proposed(candidates: list[CandidateInsight]) -> None:
    """The planted correlation, group difference and trend all reach the gateway."""
    planted = _by_variables(candidates, "age", "bmi")
    assert planted is not None and planted.claim_type is ClaimType.CORRELATION

    difference = _by_variables(candidates, "area", "income")
    assert difference is not None and difference.claim_type is ClaimType.GROUP_DIFFERENCE

    rising = _by_variables(candidates, "month", "visits")
    assert rising is not None and rising.claim_type is ClaimType.TREND


def test_pure_noise_pairs_are_not_proposed(candidates: list[CandidateInsight]) -> None:
    """noise_a/noise_b and the decoy carry no in-sample signal to propose."""
    assert _by_variables(candidates, "noise_a", "noise_b") is None
    assert _by_variables(candidates, "age", "decoy") is None


def test_nothing_is_marked_verified(candidates: list[CandidateInsight]) -> None:
    """The proposer never self-certifies (SCOPE_P 3, 5)."""
    verdict_shaped = {"p_value", "q_value", "verdict", "evidence_score", "verified", "proof"}

    assert candidates
    for candidate in candidates:
        assert not verdict_shaped & set(candidate.analysis_evidence)
        assert candidate.analysis_evidence["source"].endswith("not a test result")


def test_every_candidate_survives_the_gateway_admissibility_screen(
    candidates: list[CandidateInsight], frame: pd.DataFrame
) -> None:
    """The handoff criterion: the gateway accepts the whole batch, unpatched.

    This is the one cross-module import in the analysis suite, and it is the point of
    the exercise -- a claim template that trips the universal or causal vocabulary
    should fail here, not in a run.
    """
    columns = [str(name) for name in frame.columns]

    refused = {
        candidate.insight_id: screen(candidate, columns).reason
        for candidate in candidates
        if not screen(candidate, columns).admissible
    }
    assert refused == {}


# --- the contract ----------------------------------------------------------


def test_every_candidate_is_the_shared_contract_model(
    candidates: list[CandidateInsight],
) -> None:
    """Imported from `pramana.contracts`, never redefined (analysis hard rule 1)."""
    assert candidates
    for candidate in candidates:
        assert type(candidate) is CandidateInsight
        # Round-tripping proves it validates as itself, not merely that it was built.
        assert CandidateInsight.model_validate(candidate.model_dump()) == candidate


def test_insight_ids_are_unique_within_a_batch(candidates: list[CandidateInsight]) -> None:
    """"Unique per run" is what BH-FDR keys results by; a duplicate loses a q-value."""
    ids = [candidate.insight_id for candidate in candidates]

    assert len(set(ids)) == len(ids)


def test_group_difference_orders_variables_grouping_first(
    candidates: list[CandidateInsight],
) -> None:
    """The gateway groups by VAR_X and measures VAR_Y; the reverse tests another claim."""
    difference = _by_variables(candidates, "area", "income")

    assert difference is not None
    assert difference.variables == ["area", "income"]


def test_trend_orders_variables_time_axis_first(candidates: list[CandidateInsight]) -> None:
    rising = _by_variables(candidates, "month", "visits")

    assert rising is not None
    assert rising.variables == ["month", "visits"]


def test_a_two_level_difference_names_the_higher_group_and_asserts_it(
    candidates: list[CandidateInsight], frame: pd.DataFrame
) -> None:
    """Sentence and signed effect must agree, or the gate can REFUTE a true claim."""
    difference = _by_variables(candidates, "area", "income")
    medians = frame.groupby("area")["income"].median()

    assert difference is not None
    assert difference.reference_group == medians.idxmax()
    assert difference.asserted_direction is Direction.POSITIVE
    assert difference.reference_group is not None
    assert difference.reference_group in difference.claim


def test_a_multi_level_difference_asserts_no_direction(
    candidates: list[CandidateInsight],
) -> None:
    """"These three regions differ" has no direction to have."""
    difference = _by_variables(candidates, "region", "visits")

    assert difference is not None
    assert difference.asserted_direction is None
    assert difference.reference_group is None


def test_correlation_direction_matches_the_sign_of_the_exploratory_statistic(
    candidates: list[CandidateInsight],
) -> None:
    for candidate in candidates:
        if candidate.claim_type is not ClaimType.CORRELATION:
            continue
        raw = float(candidate.analysis_evidence["raw_value"])
        expected = Direction.POSITIVE if raw > 0 else Direction.NEGATIVE
        assert candidate.asserted_direction is expected


def test_dataset_ref_is_carried_through(candidates: list[CandidateInsight]) -> None:
    assert candidates
    assert all(candidate.dataset_ref == DATASET_REF for candidate in candidates)


# --- fail-closed -----------------------------------------------------------


def test_a_frame_below_min_observations_proposes_nothing(config: AnalysisConfig) -> None:
    """Too little data is not a licence to propose; the gate could only shrug at it."""
    rng = np.random.default_rng(3)
    n_rows = config.hypotheses.min_observations - 1
    tiny = pd.DataFrame(
        {"x": rng.normal(size=n_rows), "y": rng.normal(size=n_rows)}
    )
    tiny["y"] = tiny["x"] * 2.0 + 0.01  # a perfect relationship, and still not enough rows

    schema, candidates = analyse(tiny, dataset_ref="tiny", config=config)

    assert candidates == []


def test_columns_schema_inference_refused_are_never_named_in_a_claim(
    config: AnalysisConfig,
) -> None:
    """An unusable column cannot become a variable, however strong the association."""
    n_rows = 200
    rng = np.random.default_rng(11)
    measurement = rng.normal(50.0, 5.0, size=n_rows)
    frame = pd.DataFrame(
        {
            "record_id": np.arange(n_rows),  # id-like: excluded
            "notes": [f"free text {index}" for index in range(n_rows)],  # unknown: excluded
            "measurement": measurement,
            "paired": measurement * 1.5 + rng.normal(0.0, 1.0, size=n_rows),
        }
    )

    schema, candidates = analyse(frame, dataset_ref="synthetic", config=config)

    named = {column for candidate in candidates for column in candidate.variables}
    assert named == {"measurement", "paired"}
    assert schema.columns["record_id"].usable_for_hypotheses is False


def test_a_constant_column_is_never_proposed(config: AnalysisConfig) -> None:
    """Every association with a constant is exactly zero -- an arithmetic certainty."""
    n_rows = 200
    rng = np.random.default_rng(13)
    frame = pd.DataFrame(
        {
            "flat": np.full(n_rows, 7.0),
            "varying": rng.normal(size=n_rows),
            "grouping": rng.choice(["a", "b"], size=n_rows),
        }
    )

    _, candidates = analyse(frame, dataset_ref="synthetic", config=config)

    assert all("flat" not in candidate.variables for candidate in candidates)


def test_a_level_too_small_to_compare_is_dropped_not_merged(
    config: AnalysisConfig,
) -> None:
    """Merging would invent a group; dropping shrinks the claim to what the data holds."""
    rng = np.random.default_rng(17)
    labels = ["a"] * 100 + ["b"] * 100 + ["c"] * (config.hypotheses.min_group_size - 1)
    values = rng.normal(size=len(labels))
    values[: 100] += 3.0
    frame = pd.DataFrame({"grouping": labels, "value": values})

    _, candidates = analyse(frame, dataset_ref="synthetic", config=config)
    difference = _by_variables(candidates, "grouping", "value")

    assert difference is not None
    assert difference.analysis_evidence["group_levels"] == ["a", "b"]


def test_emit_refuses_verdict_shaped_evidence() -> None:
    """A p-value in `analysis_evidence` is the proposer claiming to have judged."""
    with pytest.raises(ValueError, match="verdict-shaped"):
        emit(
            strategy="correlation",
            claim="y is associated with x",
            claim_type=ClaimType.CORRELATION,
            variables=["x", "y"],
            dataset_ref=DATASET_REF,
            evidence={"stat": "spearman_rho", "raw_value": 0.4, "p_value": 0.01},
        )


def test_emit_drops_a_candidate_the_contract_refuses() -> None:
    """A malformed candidate is dropped, not raised -- one bad pair cannot lose a scan."""
    assert (
        emit(
            strategy="correlation",
            claim="x is associated with x",
            claim_type=ClaimType.CORRELATION,
            variables=["x", "x"],
            dataset_ref=DATASET_REF,
            evidence={"stat": "spearman_rho", "raw_value": 1.0},
        )
        is None
    )


def test_usable_pair_refuses_a_thin_or_constant_pair() -> None:
    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0], "y": [1.0, 1.0, 1.0, 1.0]})

    assert usable_pair(frame, "x", "y", min_observations=10) is None  # too few rows
    assert usable_pair(frame, "x", "y", min_observations=2) is None  # y is constant


def test_usable_pair_drops_rows_pairwise() -> None:
    """The same rows the gateway's template will see, so the hint describes the test."""
    frame = pd.DataFrame({"x": [1.0, 2.0, None, 4.0], "y": [1.0, None, 3.0, 4.0]})

    pair = usable_pair(frame, "x", "y", min_observations=2)

    assert pair is not None
    assert len(pair) == 2


# --- the cap ---------------------------------------------------------------


def test_the_batch_is_capped(frame: pd.DataFrame, schema: SchemaProfile) -> None:
    """BH divides by the family size; an uncapped scan poisons its own signal."""
    config = load_config().hypotheses.model_copy(update={"max_candidates_per_run": 2})

    candidates = generate_candidates(frame, schema, config, dataset_ref=DATASET_REF)

    assert len(candidates) == 2


def test_the_cap_keeps_the_largest_exploratory_effects(
    frame: pd.DataFrame, schema: SchemaProfile, config: AnalysisConfig
) -> None:
    uncapped = generate_candidates(
        frame, schema, config.hypotheses, dataset_ref=DATASET_REF
    )
    capped = generate_candidates(
        frame,
        schema,
        config.hypotheses.model_copy(update={"max_candidates_per_run": 2}),
        dataset_ref=DATASET_REF,
    )

    largest = sorted(
        uncapped, key=lambda item: -abs(float(item.analysis_evidence["raw_value"]))
    )[:2]
    assert {item.insight_id for item in capped} == {item.insight_id for item in largest}


def test_the_cap_is_deterministic(
    frame: pd.DataFrame, schema: SchemaProfile, config: AnalysisConfig
) -> None:
    """Ties break on insight_id, so an equal-effect pair cannot swap between runs."""
    capped = config.hypotheses.model_copy(update={"max_candidates_per_run": 3})

    first = generate_candidates(frame, schema, capped, dataset_ref=DATASET_REF)
    second = generate_candidates(frame, schema, capped, dataset_ref=DATASET_REF)

    assert first == second


# --- strategy toggles and the claim screen ---------------------------------


@pytest.mark.parametrize(
    ("enabled", "expected_type"),
    [
        ("correlation", ClaimType.CORRELATION),
        ("group_difference", ClaimType.GROUP_DIFFERENCE),
        ("trend", ClaimType.TREND),
    ],
)
def test_each_strategy_can_be_switched_off_independently(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    config: AnalysisConfig,
    enabled: str,
    expected_type: ClaimType,
) -> None:
    only = config.hypotheses.model_copy(
        update={
            "strategies": config.hypotheses.strategies.model_copy(
                update={
                    name: name == enabled
                    for name in ("correlation", "group_difference", "trend")
                }
            )
        }
    )

    candidates = generate_candidates(frame, schema, only, dataset_ref=DATASET_REF)

    assert candidates
    assert {candidate.claim_type for candidate in candidates} == {expected_type}


def test_a_claim_screen_drops_what_it_refuses(
    frame: pd.DataFrame, schema: SchemaProfile, config: AnalysisConfig
) -> None:
    """The seam for the gateway's own screen: refuse earlier, spend nothing on it."""

    def refuse_trends(claim: str, claim_type: ClaimType, variables: list[str]) -> bool:
        return claim_type is not ClaimType.TREND

    candidates = generate_candidates(
        frame, schema, config.hypotheses, dataset_ref=DATASET_REF, claim_screen=refuse_trends
    )

    assert candidates
    assert all(candidate.claim_type is not ClaimType.TREND for candidate in candidates)


def test_the_gateway_screen_itself_can_be_passed_as_the_claim_screen(
    frame: pd.DataFrame, schema: SchemaProfile, config: AnalysisConfig
) -> None:
    """Orchestration imports both modules; wiring the real screen in must work."""
    columns = [str(name) for name in frame.columns]

    def gateway_screen(claim: str, claim_type: ClaimType, variables: list[str]) -> bool:
        return screen(
            CandidateInsight(
                insight_id="screen-probe",
                claim=claim,
                claim_type=claim_type,
                variables=variables,
                dataset_ref=DATASET_REF,
            ),
            columns,
        ).admissible

    screened = generate_candidates(
        frame, schema, config.hypotheses, dataset_ref=DATASET_REF, claim_screen=gateway_screen
    )
    unscreened = generate_candidates(
        frame, schema, config.hypotheses, dataset_ref=DATASET_REF
    )

    assert screened == unscreened


# --- determinism and purity ------------------------------------------------


def test_generation_is_deterministic(
    frame: pd.DataFrame, schema: SchemaProfile, config: AnalysisConfig
) -> None:
    first = generate_candidates(frame, schema, config.hypotheses, dataset_ref=DATASET_REF)
    second = generate_candidates(frame, schema, config.hypotheses, dataset_ref=DATASET_REF)

    assert first == second


def test_the_frame_is_never_modified(frame: pd.DataFrame, config: AnalysisConfig) -> None:
    before = frame.copy(deep=True)

    analyse(frame, dataset_ref=DATASET_REF, config=config)

    pd.testing.assert_frame_equal(frame, before)


def test_analyse_returns_the_schema_the_candidates_were_built_from(
    frame: pd.DataFrame, config: AnalysisConfig
) -> None:
    """A caller can report exactly which columns were skipped, and why."""
    schema, candidates = analyse(frame, dataset_ref=DATASET_REF, config=config)

    assert schema == infer_schema(frame, config.schema_inference)
    assert candidates == generate_candidates(
        frame, schema, config.hypotheses, dataset_ref=DATASET_REF
    )


def test_analyse_falls_back_to_the_shipped_config(frame: pd.DataFrame) -> None:
    assert analyse(frame, dataset_ref=DATASET_REF) == analyse(
        frame, dataset_ref=DATASET_REF, config=load_config()
    )


def test_slug_is_stable_and_log_safe() -> None:
    assert slug("correlation", "BMI (kg/m^2)", "age") == "correlation-bmi-kg-m-2-age"
    assert slug("", "") == "unnamed"


# --- per-strategy pre-filters ----------------------------------------------


def test_correlation_honours_its_exploratory_floor(
    frame: pd.DataFrame, schema: SchemaProfile, config: AnalysisConfig
) -> None:
    strict = config.hypotheses.model_copy(update={"min_abs_correlation": 0.99})

    assert (
        correlation.propose(frame, schema, strict, dataset_ref=DATASET_REF) == []
    )


def test_group_difference_honours_its_exploratory_floor(
    frame: pd.DataFrame, schema: SchemaProfile, config: AnalysisConfig
) -> None:
    strict = config.hypotheses.model_copy(update={"min_group_effect": 0.99})

    assert group_difference.propose(frame, schema, strict, dataset_ref=DATASET_REF) == []


def test_trend_honours_its_exploratory_floor(
    frame: pd.DataFrame, schema: SchemaProfile, config: AnalysisConfig
) -> None:
    strict = config.hypotheses.model_copy(update={"min_abs_trend_tau": 0.99})

    assert trend.propose(frame, schema, strict, dataset_ref=DATASET_REF) == []


def test_a_frame_with_no_time_axis_yields_no_trend_candidates(
    config: AnalysisConfig,
) -> None:
    """"Rises over time" needs a time; substituting row order would invent one."""
    rng = np.random.default_rng(23)
    values = rng.normal(size=200)
    frame = pd.DataFrame({"measure_a": values, "measure_b": values * 2 + rng.normal(size=200)})

    schema = infer_schema(frame, config.schema_inference)

    assert trend.propose(frame, schema, config.hypotheses, dataset_ref="synthetic") == []


def test_a_real_datetime_column_produces_a_trend_candidate(config: AnalysisConfig) -> None:
    n_rows = 200
    rng = np.random.default_rng(29)
    frame = pd.DataFrame(
        {
            "visit_date": pd.date_range("2021-01-01", periods=n_rows, freq="D"),
            "reading": np.linspace(10.0, 40.0, n_rows) + rng.normal(0.0, 1.0, size=n_rows),
        }
    )

    _, candidates = analyse(frame, dataset_ref="synthetic", config=config)
    rising = _by_variables(candidates, "visit_date", "reading")

    assert rising is not None
    assert rising.claim_type is ClaimType.TREND
    assert rising.asserted_direction is Direction.POSITIVE
    assert rising.analysis_evidence["stat"] == "kendall_tau_b"
