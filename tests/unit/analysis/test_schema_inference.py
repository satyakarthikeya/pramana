"""Deterministic column classification (SCOPE_P_Rohith.md 2, component 2).

The tests are organised around the two properties that matter downstream:

  * roles are inferred from VALUES, so the classifier survives NHANES's `RIDAGEYR`
    and NFHS-5's `v024` without a lookup table of column names;
  * it fails CLOSED -- an unclassifiable column comes back `UNKNOWN` and unusable,
    never as a plausible-looking guess that becomes a hypothesis.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.analysis.config import SchemaInferenceConfig, load_config
from pramana.analysis.schema_inference import (
    USABLE_ROLES,
    ColumnProfile,
    ColumnRole,
    SchemaProfile,
    describe_unusable,
    infer_column,
    infer_schema,
    schema_profile,
)

N_ROWS = 120


@pytest.fixture
def config() -> SchemaInferenceConfig:
    """The shipped cutoffs -- the tests assert against what the project actually runs."""
    return load_config().schema_inference


@pytest.fixture
def frame() -> pd.DataFrame:
    """One column per role, with deliberately opaque names.

    Not a single name here tells you the type. If the classifier needs the name, it
    fails this fixture, which is the point: the demo datasets name things `RIDAGEYR`.
    """
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "seqn": np.arange(10_000, 10_000 + N_ROWS),
            "ridageyr": rng.normal(45.0, 14.0, size=N_ROWS),
            "riagendr": rng.choice(["m", "f"], size=N_ROWS),
            "dmdeduc2": rng.integers(1, 6, size=N_ROWS),
            "v024": pd.date_range("2020-01-01", periods=N_ROWS, freq="D"),
            "v025": pd.date_range("2019-01-01", periods=N_ROWS, freq="D").astype(str),
            "v026": [f"free text note number {index}" for index in range(N_ROWS)],
            "survey_month": rng.integers(1, 13, size=N_ROWS),
        }
    )


# --- roles come from values ------------------------------------------------


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ("seqn", ColumnRole.ID_LIKE),
        ("ridageyr", ColumnRole.NUMERIC),
        ("riagendr", ColumnRole.CATEGORICAL),
        ("dmdeduc2", ColumnRole.ORDINAL),
        ("v024", ColumnRole.DATETIME),
        ("v025", ColumnRole.DATETIME),
        ("v026", ColumnRole.UNKNOWN),
        ("survey_month", ColumnRole.ORDINAL),
    ],
)
def test_each_role_is_inferred_from_the_values(
    frame: pd.DataFrame, config: SchemaInferenceConfig, column: str, expected: ColumnRole
) -> None:
    assert infer_schema(frame, config).role_of(column) is expected


def test_every_column_gets_exactly_one_profile(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    schema = infer_schema(frame, config)

    assert list(schema.columns) == [str(name) for name in frame.columns]
    assert schema.n_rows == len(frame)
    assert schema.n_columns == len(frame.columns)


def test_every_profile_carries_a_reason(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    """A role with no reason cannot be reviewed, and every role here gets reviewed."""
    for profile in infer_schema(frame, config).columns.values():
        assert profile.reasons
        assert all(reason.strip() for reason in profile.reasons)


def test_the_frame_is_never_modified(frame: pd.DataFrame, config: SchemaInferenceConfig) -> None:
    before = frame.copy(deep=True)

    infer_schema(frame, config)

    pd.testing.assert_frame_equal(frame, before)


def test_inference_is_deterministic(frame: pd.DataFrame, config: SchemaInferenceConfig) -> None:
    assert infer_schema(frame, config) == infer_schema(frame, config)


# --- fail-closed -----------------------------------------------------------


def test_a_column_below_min_non_null_is_unknown_and_unusable(
    config: SchemaInferenceConfig,
) -> None:
    """Too little data to classify is not a licence to guess."""
    series = pd.Series([1.0, 2.0, 3.0] + [None] * 50)

    profile = infer_column(series, "sparse", config)

    assert profile.role is ColumnRole.UNKNOWN
    assert profile.usable_for_hypotheses is False
    assert "min_non_null" in " ".join(profile.reasons)


def test_a_role_below_min_confidence_is_demoted_rather_than_kept(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    """Raise the bar above the ordinal heuristic's confidence and it must give way."""
    strict = config.model_copy(update={"min_confidence": 0.95})

    profile = infer_schema(frame, strict).columns["dmdeduc2"]

    assert profile.role is ColumnRole.UNKNOWN
    assert profile.usable_for_hypotheses is False
    assert "min_confidence" in " ".join(profile.reasons)


def test_high_cardinality_free_text_is_refused_not_guessed(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    """Guessing CATEGORICAL here would hand the gateway a 120-level grouping."""
    profile = infer_schema(frame, config).columns["v026"]

    assert profile.role is ColumnRole.UNKNOWN
    assert profile.usable_for_hypotheses is False


@pytest.mark.parametrize(
    "values",
    [
        pytest.param([], id="empty"),
        pytest.param([None] * 60, id="all-null"),
        pytest.param([4.0] * 60, id="constant"),
    ],
)
def test_degenerate_columns_do_not_raise(
    config: SchemaInferenceConfig, values: list[object]
) -> None:
    profile = infer_column(pd.Series(values, dtype="object"), "degenerate", config)

    assert profile.role is ColumnRole.UNKNOWN
    assert profile.usable_for_hypotheses is False


def test_usable_is_exactly_role_and_confidence(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    """The single flag consumers honour must mean what it says."""
    for profile in infer_schema(frame, config).columns.values():
        expected = profile.role in USABLE_ROLES and profile.confidence >= config.min_confidence
        assert profile.usable_for_hypotheses is expected


def test_identifier_columns_are_never_usable(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    """A correlation with a record number is a claim about row order."""
    assert infer_schema(frame, config).columns["seqn"].usable_for_hypotheses is False


def test_a_continuous_measurement_is_not_called_an_identifier(
    config: SchemaInferenceConfig,
) -> None:
    """Every value distinct is what a real measurement looks like too."""
    series = pd.Series(np.linspace(1.5, 99.5, N_ROWS))

    assert infer_column(series, "bmxbmi", config).role is ColumnRole.NUMERIC


def test_an_integer_year_is_not_mistaken_for_a_timestamp(
    config: SchemaInferenceConfig,
) -> None:
    """2011 parses as a nanosecond epoch; that is not a reason to call it a date."""
    series = pd.Series([2011, 2012, 2013, 2014] * 30)

    assert infer_column(series, "survey_year", config).role is ColumnRole.ORDINAL


# --- the time axis ---------------------------------------------------------


def test_time_like_marks_datetimes_and_named_ordinals(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    schema = infer_schema(frame, config)

    assert schema.columns["v024"].is_time_like is True
    assert schema.columns["survey_month"].is_time_like is True
    # Same shape, same dtype, no time in the name: an ordinal, not an axis.
    assert schema.columns["dmdeduc2"].is_time_like is False


def test_name_tokens_match_whole_words_only(config: SchemaInferenceConfig) -> None:
    """`avoidance` contains "id"; a substring match would call it an identifier."""
    series = pd.Series(np.arange(N_ROWS))

    assert infer_column(series, "avoidance", config).role is not ColumnRole.ID_LIKE
    assert infer_column(series, "PatientID", config).role is ColumnRole.ID_LIKE


# --- accessors and serialisation -------------------------------------------


def test_levels_are_recorded_for_groupings_only(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    schema = infer_schema(frame, config)

    assert schema.columns["riagendr"].levels == ["f", "m"]
    assert schema.columns["ridageyr"].levels == []


def test_usable_filters_by_role_and_keeps_column_order(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    schema = infer_schema(frame, config)

    assert schema.usable(ColumnRole.NUMERIC) == ["ridageyr"]
    assert schema.usable(ColumnRole.CATEGORICAL, ColumnRole.ORDINAL) == [
        "riagendr",
        "dmdeduc2",
        "survey_month",
    ]
    assert "seqn" not in schema.usable()


def test_role_of_an_absent_column_is_unknown(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    assert infer_schema(frame, config).role_of("not_a_column") is ColumnRole.UNKNOWN


def test_ambiguous_lists_the_refiner_queue(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    assert infer_schema(frame, config).ambiguous == ["v026"]


def test_describe_unusable_explains_every_exclusion(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    """Failing closed is only reviewable if the skip is reportable."""
    schema = infer_schema(frame, config)
    lines = describe_unusable(schema)

    excluded = {name for name, p in schema.columns.items() if not p.usable_for_hypotheses}
    assert len(lines) == len(excluded)
    assert all(any(line.startswith(f"{name}:") for line in lines) for name in excluded)


def test_schema_profile_round_trips_through_json(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    import json

    payload = schema_profile(frame, config)

    assert SchemaProfile.model_validate(json.loads(json.dumps(payload))) == infer_schema(
        frame, config
    )


# --- the Gemma seam --------------------------------------------------------


class _Refiner:
    """A stand-in for the local model. Records what it was asked about."""

    def __init__(self, answer: ColumnRole | None) -> None:
        self.answer = answer
        self.asked: list[str] = []

    def refine(self, profile: ColumnProfile) -> ColumnRole | None:
        self.asked.append(profile.name)
        return self.answer


class _ExplodingRefiner:
    def refine(self, profile: ColumnProfile) -> ColumnRole | None:
        raise RuntimeError("ollama is not running")


def test_the_refiner_is_offered_ambiguous_columns_only(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    """`use_llm_for_ambiguous_only`: heuristics decide everything they can."""
    refiner = _Refiner(ColumnRole.CATEGORICAL)

    infer_schema(frame, config, refiner=refiner)

    assert refiner.asked == ["v026"]


def test_a_refined_role_is_believed_but_never_promoted(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    schema = infer_schema(frame, config, refiner=_Refiner(ColumnRole.CATEGORICAL))
    profile = schema.columns["v026"]

    assert profile.role is ColumnRole.CATEGORICAL
    assert profile.usable_for_hypotheses is True
    assert profile.confidence == config.min_confidence


def test_a_declining_refiner_leaves_the_column_unknown(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    """Returning None must stay a first-class answer, not an error."""
    schema = infer_schema(frame, config, refiner=_Refiner(None))

    assert schema.columns["v026"].role is ColumnRole.UNKNOWN
    assert schema.columns["v026"].usable_for_hypotheses is False


def test_a_refiner_that_raises_cannot_fail_the_run(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    """The local model being down is not a reason to lose the whole schema."""
    schema = infer_schema(frame, config, refiner=_ExplodingRefiner())

    assert schema.columns["v026"].role is ColumnRole.UNKNOWN
    assert "raised" in " ".join(schema.columns["v026"].reasons)
    assert schema.columns["ridageyr"].role is ColumnRole.NUMERIC


def test_a_refiner_cannot_widen_what_is_usable(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    """An ID_LIKE or UNKNOWN answer is not a usable role, whoever said it."""
    for answer in (ColumnRole.ID_LIKE, ColumnRole.UNKNOWN):
        schema = infer_schema(frame, config, refiner=_Refiner(answer))

        assert schema.columns["v026"].usable_for_hypotheses is False


def test_no_refiner_means_no_refinement(
    frame: pd.DataFrame, config: SchemaInferenceConfig
) -> None:
    """The shipped default: no Gemma client wired in, so ambiguity stays ambiguous."""
    assert infer_schema(frame, config).columns["v026"].role is ColumnRole.UNKNOWN
