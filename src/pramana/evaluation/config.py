"""Loads `configs/evaluation.yaml` -- the one place the harness's schedule and seeds live.

Strict for the same reason `verification/config.py` is: `extra="forbid"` and no defaults,
so a typo'd key and a deleted key both fail at load time with the key named. A schedule
that quietly reverted to a default would mean the benchmark that produced the report is
not the benchmark the config describes (AGENTS.md 3.3).

Effect sizes are stored as multiples of the gate's own per-metric floor
(`multiplier_of_floor`), never as numbers in the gate's units. The floors are read from
the verification config when a dataset is built (`planted.py`), so the schedule keeps
straddling the decision boundary when the bands are recalibrated.

Owner: P.P. Satya Karthikeya
Scope: src/pramana/evaluation/SPEC.md 2
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

#: Repository root: evaluation -> pramana -> src -> root.
_REPO_ROOT = Path(__file__).resolve().parents[3]

#: The config the harness runs on unless a caller passes another path.
DEFAULT_EVALUATION_CONFIG_PATH = _REPO_ROOT / "configs" / "evaluation.yaml"


class RelationshipType(StrEnum):
    """The three relationship shapes SPEC.md 2 step 3 injects."""

    MONOTONIC = "monotonic"  # numeric pair, gated on Spearman's rho
    SHIFT = "shift"  # location shift across a binary categorical, gated on Cliff's delta
    TREND = "trend"  # numeric against a time/ordinal column, gated on Kendall's tau-b


class SignDirection(StrEnum):
    """Direction of an injected relationship (same words as `contracts.Direction`)."""

    POSITIVE = "positive"
    NEGATIVE = "negative"


class EffectLevel(BaseModel):
    """A named effect size, as a multiple of the gate's floor for the metric."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    multiplier_of_floor: float = Field(gt=0.0)


class PlantedConfig(BaseModel):
    """The logged schedule `k`, types, directions and effect sizes are drawn from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_seed: int
    k_per_dataset: list[int] = Field(min_length=1)
    relationship_cycle: list[RelationshipType] = Field(min_length=1)
    direction_cycle: list[SignDirection] = Field(min_length=1)
    effect_levels: list[EffectLevel] = Field(min_length=1)
    calibration_tolerance: float = Field(gt=0.0)


class ExtractShape(BaseModel):
    """Benchmark-like extract dimensions (measurement script and tests)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_rows: int = Field(gt=0)
    n_numeric: int = Field(ge=0)
    n_binary_categorical: int = Field(ge=0)
    n_multilevel_categorical: int = Field(ge=0)
    n_ordinal: int = Field(ge=0)

    @property
    def n_columns(self) -> int:
        return (
            self.n_numeric
            + self.n_binary_categorical
            + self.n_multilevel_categorical
            + self.n_ordinal
        )


class ConditionsConfig(BaseModel):
    """Which model the analysis step is configured for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_model: str = Field(min_length=1)


class MeasurementConfig(BaseModel):
    """Parameters of the permutation-cost measurement (docs/OPEN_ISSUES.md item 5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    benchmark_datasets: int = Field(gt=0)
    datasets_timed: int = Field(gt=0)
    candidates_timed_per_claim_type: int = Field(gt=0)


class EvaluationConfig(BaseModel):
    """Everything the evaluation harness is allowed to be configured with."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    planted: PlantedConfig
    extract_shape: ExtractShape
    conditions: ConditionsConfig
    measurement: MeasurementConfig


def load_evaluation_config(
    path: Path | str = DEFAULT_EVALUATION_CONFIG_PATH,
) -> EvaluationConfig:
    """Load and validate the evaluation config.

    Guarantees: every value the harness uses came from `path`; a missing, unknown or
    out-of-range key raises `ValidationError` before any dataset is built.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return EvaluationConfig.model_validate(raw)
