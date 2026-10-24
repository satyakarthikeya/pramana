"""Limits and grids for the Measured tier, read from `configs/analysis.yaml` (`measured:`).

Strict like the Exact tier's loader: no defaults, unknown keys refused, so a deleted or
misspelt cutoff fails at load instead of quietly substituting one nobody chose.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.config import DEFAULT_CONFIG_PATH


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LeakageConfig(_Strict):
    id_unique_ratio: float = Field(gt=0.5, le=1)
    proxy_cutoff: float = Field(gt=0, lt=1)
    proxy_folds: int = Field(ge=2, le=10)
    identity_rel_tolerance: float = Field(gt=0, lt=0.1)
    identity_min_match: float = Field(gt=0.5, le=1)
    identity_min_rows: int = Field(ge=3, le=100000)
    max_identity_columns: int = Field(ge=2, le=200)


class ImportanceConfig(_Strict):
    correlated_rho: float = Field(gt=0, le=1)
    repeats: int = Field(ge=1, le=50)


class GridConfig(_Strict):
    ridge_alpha: list[float] = Field(min_length=1)
    forest_trees: int = Field(ge=5, le=1000)
    forest_depth: list[int | None] = Field(min_length=1)
    boosting_trees: int = Field(ge=5, le=1000)
    boosting_depth: list[int] = Field(min_length=1)
    boosting_rate: list[float] = Field(min_length=1)
    svm_c: list[float] = Field(min_length=1)
    svm_max_rows: int = Field(ge=50, le=1000000)
    logistic_c: list[float] = Field(min_length=1)
    knn_neighbors: list[int] = Field(default=[5, 15], min_length=1)
    knn_max_rows: int = Field(default=20000, ge=50, le=1000000)


class SegmentsConfig(_Strict):
    k_min: int = Field(ge=2, le=20)
    k_max: int = Field(ge=2, le=20)
    train_fraction: float = Field(gt=0.3, lt=1)
    null_repeats: int = Field(ge=1, le=50)
    silhouette_margin: float = Field(ge=0, le=1)
    bootstrap_repeats: int = Field(ge=2, le=200)
    ari_cutoff: float = Field(gt=0, le=1)
    min_segment_share: float = Field(ge=0, lt=0.5)
    max_profile_columns: int = Field(ge=1, le=30)


class AnomaliesConfig(_Strict):
    flag_fraction: float = Field(gt=0, lt=0.5)
    seeds: int = Field(ge=2, le=50)
    robust_z: float = Field(gt=0, le=20)
    rank_stability_cutoff: float = Field(gt=0, le=1)
    max_listed: int = Field(ge=1, le=100)
    max_shared_columns: int = Field(ge=1, le=20)
    shared_min_shift: float = Field(gt=0, le=20)


class ForecastConfig(_Strict):
    min_periods: int = Field(ge=4, le=1000)
    min_cycles: int = Field(ge=2, le=10)
    origins: int = Field(ge=2, le=50)
    min_origins: int = Field(ge=2, le=50)
    horizon: dict[str, int]
    seasonal_length: dict[str, int]
    interval_level: float = Field(gt=0.5, lt=1)
    lift_floor_relative: float = Field(ge=0, lt=1)
    max_gap_fraction: float = Field(ge=0, lt=1)
    max_chart_points: int = Field(ge=12, le=1000)


class ThresholdConfig(_Strict):
    grid_points: int = Field(ge=3, le=200)
    edge_fraction: float = Field(gt=0, lt=0.5)
    bootstrap_repeats: int = Field(ge=2, le=500)
    max_chart_points: int = Field(ge=5, le=200)


class ComponentsConfig(_Strict):
    null_repeats: int = Field(default=20, ge=2, le=200)
    null_quantile: float = Field(default=0.95, gt=0.5, lt=1)
    bootstrap_repeats: int = Field(default=20, ge=2, le=200)
    stability_cutoff: float = Field(default=0.9, gt=0.5, le=1)
    max_loadings: int = Field(default=3, ge=1, le=10)


class MeasuredConfig(_Strict):
    enabled: bool
    seed: int
    max_rows: int = Field(ge=50, le=1000000)
    max_features: int = Field(ge=1, le=100)
    max_missing_fraction: float = Field(gt=0, le=1)
    max_categorical_levels: int = Field(ge=2, le=100)
    time_budget_seconds: float = Field(gt=0, le=3600)
    min_rows: int = Field(ge=10, le=100000)
    outer_folds: int = Field(ge=2, le=20)
    inner_folds: int = Field(ge=2, le=10)
    min_class_rows: int = Field(ge=2, le=100000)
    max_class_levels: int = Field(ge=2, le=50)
    lift_floor: float = Field(ge=0, lt=1)
    too_good_cutoff: float = Field(gt=0.5, le=1)
    leakage: LeakageConfig
    importance: ImportanceConfig
    grids: GridConfig
    segments: SegmentsConfig
    anomalies: AnomaliesConfig
    forecast: ForecastConfig
    threshold: ThresholdConfig
    components: ComponentsConfig = Field(default_factory=ComponentsConfig)


def load_measured_config(path: Path | str = DEFAULT_CONFIG_PATH) -> MeasuredConfig:
    """The `measured:` section of the analysis config. Raises on a missing or unknown key."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["measured"]
    if flag := os.getenv("PRAMANA_MEASURED_ENABLED"):
        raw["enabled"] = flag.strip().lower() in {"1", "true", "yes", "on"}
    return MeasuredConfig.model_validate(raw)
