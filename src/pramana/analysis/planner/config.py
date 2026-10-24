"""Budgets for the planner, read from `configs/analysis.yaml` (`planner:`).

Strict like the other loaders: no defaults, unknown keys refused, so a deleted or misspelt
budget fails at load instead of quietly substituting one nobody chose.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.config import DEFAULT_CONFIG_PATH


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CheapMeasured(_Strict):
    max_rows: int = Field(ge=50, le=5000)
    outer_folds: int = Field(ge=2, le=5)
    inner_folds: int = Field(ge=2, le=3)
    time_budget_seconds: float = Field(gt=0, le=300)


class PlannerConfig(_Strict):
    max_claims: int = Field(ge=1, le=50)
    max_measured_requests: int = Field(ge=0, le=20)
    max_narrative_focus: int = Field(ge=0, le=20)
    max_exact_figures: int = Field(ge=1, le=40)
    max_measured_figures: int = Field(ge=0, le=20)
    max_columns: int = Field(ge=2, le=60)
    max_levels: int = Field(ge=2, le=20)
    max_prompt_chars: int = Field(ge=2000, le=100000)
    max_output_tokens: int = Field(ge=256, le=4096)
    max_total_tokens: int = Field(ge=2000, le=200000)
    max_repair_turns: int = Field(ge=0, le=1)
    temperature: float = Field(ge=0, le=1)
    cheap_measured: CheapMeasured


def load_planner_config(path: Path | str = DEFAULT_CONFIG_PATH) -> PlannerConfig:
    """The `planner:` section of the analysis config. Raises on a missing or unknown key."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["planner"]
    return PlannerConfig.model_validate(raw)
