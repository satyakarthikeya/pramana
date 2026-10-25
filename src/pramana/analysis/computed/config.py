"""Limits for the Exact tier, read from `configs/analysis.yaml` (`computed:`)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.config import DEFAULT_CONFIG_PATH


class ComputedConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sector_engine: Literal["api", "rules"]
    summary_engine: Literal["api", "template"]
    analyst_engine: Literal["agent", "api", "template"] = "template"
    max_chart_points: int = Field(ge=12, le=1000)
    max_measures: int = Field(ge=1, le=50)
    max_segments: int = Field(ge=2, le=100)
    max_outliers_listed: int = Field(ge=1, le=50)
    max_margin_columns: int = Field(ge=0, le=10)
    max_margin_levels: int = Field(ge=2, le=50)
    outlier_robust_z: float = Field(gt=0, le=20)
    seasonality_min_cycles: int = Field(ge=2, le=10)
    min_prevalence_rows: int = Field(ge=1, le=100000)
    min_group_rows: int = Field(ge=1, le=100000)
    identity_min_rows: int = Field(ge=3, le=100000)
    identity_rel_tolerance: float = Field(gt=0, lt=0.1)
    identity_min_match: float = Field(gt=0.5, le=1)
    lead_items: int = Field(default=8, ge=1, le=30)
    max_questions: int = Field(default=5, ge=0, le=10)
    segment_growth_min_share: float = Field(default=0.02, ge=0, lt=1)
    customer_min_customers: int = Field(default=10, ge=2, le=100000)
    customer_top_n: int = Field(default=10, ge=1, le=1000)
    story_weights: dict[str, float] = Field(default_factory=dict)


def load_computed_config(path: Path | str = DEFAULT_CONFIG_PATH) -> ComputedConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["computed"]
    if engine := os.getenv("PRAMANA_SECTOR_ENGINE"):
        raw["sector_engine"] = engine
    if engine := os.getenv("PRAMANA_SUMMARY_ENGINE"):
        raw["summary_engine"] = engine
    if engine := os.getenv("PRAMANA_ANALYST_ENGINE"):
        raw["analyst_engine"] = engine
    return ComputedConfig.model_validate(raw)
