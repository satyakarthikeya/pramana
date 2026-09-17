"""`configs/analysis.yaml` and its loader.

The loader is strict on purpose, so most of these tests are about what it REFUSES.
A threshold that silently falls back to a default is a run whose report no longer
describes it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from pramana.analysis.config import (
    DEFAULT_CONFIG_PATH,
    AnalysisConfig,
    HypothesesConfig,
    SchemaInferenceConfig,
    load_config,
)


@pytest.fixture
def raw_config() -> dict[str, Any]:
    """The shipped config, as a plain mapping, for mutation in a test."""
    return dict(yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")))


def _write(tmp_path: Path, raw: dict[str, Any]) -> Path:
    target = tmp_path / "analysis.yaml"
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return target


def test_shipped_config_loads_and_is_frozen() -> None:
    config = load_config()

    assert isinstance(config, AnalysisConfig)
    assert config.schema_inference.model == "gemma"
    assert config.hypotheses.max_candidates_per_run >= 1
    with pytest.raises(ValidationError):
        config.hypotheses.max_candidates_per_run = 10  # type: ignore[misc]


def test_shipped_config_is_internally_consistent() -> None:
    """Every cross-field rule holds for the values the project actually ships."""
    config = load_config()

    assert config.schema_inference.ordinal_max_levels <= (
        config.schema_inference.categorical_max_levels
    )
    assert config.hypotheses.min_group_levels <= config.hypotheses.max_group_levels
    # A grouping needs enough rows per level to reach the overall floor.
    assert (
        config.hypotheses.min_group_levels * config.hypotheses.min_group_size
        <= config.hypotheses.min_observations
    )


def test_verification_tier_model_is_refused(tmp_path: Path, raw_config: dict[str, Any]) -> None:
    """AGENTS.md 2: schema inference is routine work and never runs on the gateway's model."""
    raw_config["schema_inference"]["model"] = "deepseek-v4"

    with pytest.raises(ValidationError, match="verification-tier model"):
        load_config(_write(tmp_path, raw_config))


def test_verification_tier_model_is_refused_behind_a_provider_prefix(
    tmp_path: Path, raw_config: dict[str, Any]
) -> None:
    """`deepseek/deepseek-chat` is still DeepSeek; the check matches the trailing token."""
    raw_config["schema_inference"]["model"] = "deepseek/deepseek-chat"

    with pytest.raises(ValidationError, match="verification-tier model"):
        load_config(_write(tmp_path, raw_config))


def test_local_model_names_are_accepted(tmp_path: Path, raw_config: dict[str, Any]) -> None:
    raw_config["schema_inference"]["model"] = "ollama/gemma2:9b"

    assert load_config(_write(tmp_path, raw_config)).schema_inference.model == "ollama/gemma2:9b"


def test_unknown_key_inside_a_served_section_fails_loudly(
    tmp_path: Path, raw_config: dict[str, Any]
) -> None:
    """A typo'd threshold must not be silently ignored -- it decides what gets proposed."""
    raw_config["hypotheses"]["min_abs_corelation"] = 0.2

    with pytest.raises(ValidationError, match="min_abs_corelation"):
        load_config(_write(tmp_path, raw_config))


def test_missing_key_inside_a_served_section_fails_loudly(
    tmp_path: Path, raw_config: dict[str, Any]
) -> None:
    del raw_config["schema_inference"]["min_confidence"]

    with pytest.raises(ValidationError, match="min_confidence"):
        load_config(_write(tmp_path, raw_config))


def test_sections_owned_by_other_components_are_ignored(
    tmp_path: Path, raw_config: dict[str, Any]
) -> None:
    """`ingestion`, `cleaning` and `benchmark` can evolve without touching this loader."""
    raw_config["ingestion"]["some_future_key"] = 3
    raw_config["a_whole_new_section"] = {"anything": True}

    config = load_config(_write(tmp_path, raw_config))

    assert config.schema_inference.model == "gemma"


def test_ordinal_cap_above_categorical_cap_is_refused() -> None:
    with pytest.raises(ValidationError, match="must not exceed"):
        SchemaInferenceConfig(
            use_llm_for_ambiguous_only=True,
            model="gemma",
            min_confidence=0.7,
            min_non_null=20,
            id_unique_ratio=0.95,
            categorical_max_levels=10,
            ordinal_max_levels=20,
            datetime_parse_min_ratio=0.9,
        )


def test_group_level_bounds_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="must not exceed"):
        HypothesesConfig(
            max_candidates_per_run=50,
            strategies={"correlation": True, "group_difference": True, "trend": True},
            min_abs_correlation=0.15,
            min_observations=30,
            min_group_size=10,
            min_group_levels=8,
            max_group_levels=4,
            min_group_effect=0.01,
            min_abs_trend_tau=0.1,
        )


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("schema_inference", "min_confidence", 0.0),
        ("schema_inference", "min_confidence", 1.5),
        ("schema_inference", "min_non_null", 0),
        ("schema_inference", "id_unique_ratio", 2.0),
        ("hypotheses", "max_candidates_per_run", 0),
        ("hypotheses", "min_observations", 1),
        ("hypotheses", "min_abs_correlation", -0.1),
        ("hypotheses", "min_group_size", 1),
    ],
)
def test_out_of_range_values_are_refused(
    tmp_path: Path, raw_config: dict[str, Any], section: str, key: str, value: float
) -> None:
    raw_config[section][key] = value

    with pytest.raises(ValidationError, match=key):
        load_config(_write(tmp_path, raw_config))
