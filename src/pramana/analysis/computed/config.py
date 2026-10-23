"""Limits for the Exact tier, read from `configs/analysis.yaml` (`computed:`)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.config import DEFAULT_CONFIG_PATH


class ComputedConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_measures: int = Field(ge=1, le=50)
    max_segments: int = Field(ge=2, le=100)
    max_outliers_listed: int = Field(ge=1, le=50)
    outlier_robust_z: float = Field(gt=0, le=20)
    seasonality_min_cycles: int = Field(ge=2, le=10)
    min_prevalence_rows: int = Field(ge=1, le=100000)
    min_group_rows: int = Field(ge=1, le=100000)
    identity_min_rows: int = Field(ge=3, le=100000)
    identity_rel_tolerance: float = Field(gt=0, lt=0.1)
    identity_min_match: float = Field(gt=0.5, le=1)


def load_computed_config(path: Path | str = DEFAULT_CONFIG_PATH) -> ComputedConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["computed"]
    return ComputedConfig.model_validate(raw)
