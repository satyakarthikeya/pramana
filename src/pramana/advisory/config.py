"""Thresholds for the Skeptic and the Explainer, read from one place (`configs/analysis.yaml`)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.config import DEFAULT_CONFIG_PATH


class SkepticConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool
    min_rows: int = Field(ge=10, le=100000)
    min_link_to_control: float = Field(gt=0, lt=1)
    min_drop_fraction: float = Field(gt=0, lt=1)
    min_original_rho: float = Field(ge=0, lt=1)
    min_original_eta2: float = Field(ge=0, lt=1)
    max_duplicate_rho: float = Field(gt=0, le=1)
    max_duplicate_group_link: float = Field(gt=0, le=1)
    max_controls_checked: int = Field(ge=1, le=500)
    max_caveats_per_finding: int = Field(ge=1, le=10)
    max_levels: int = Field(ge=2, le=100)
    min_level_rows: int = Field(ge=2, le=1000)
    time_budget_seconds: float = Field(gt=0, le=600)


class ExplainerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    engine: Literal["template", "api"]
    max_summary_chars: int = Field(ge=100, le=2000)
    max_output_tokens: int = Field(ge=200, le=4096)
    timeout_seconds: float = Field(ge=5, le=300)
    temperature: float = Field(ge=0, le=1)


class AdvisoryConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    skeptic: SkepticConfig
    explainer: ExplainerConfig


def load_advisory_config(path: Path | str = DEFAULT_CONFIG_PATH) -> AdvisoryConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["advisory"]
    if engine := os.getenv("PRAMANA_EXPLAINER_ENGINE"):
        raw["explainer"]["engine"] = engine
    return AdvisoryConfig.model_validate(raw)
