"""Budgets for the analysis workspace and agent, read from one place (`configs/analysis.yaml`)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.config import DEFAULT_CONFIG_PATH


class SandboxConfig(BaseModel):
    """Limits for a free-form Python run. Statistics never come from here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Off unless switched on; sandbox.py explains what protects it and what does not.
    enabled: bool
    timeout_seconds: int = Field(gt=0, le=120)
    max_memory_mb: int = Field(ge=128, le=4096)
    max_output_chars: int = Field(ge=200, le=20000)
    allowed_imports: list[str] = Field(min_length=1)


class AgentConfig(BaseModel):
    """Hard stops for the model-driven analyst, so a run can never spend without bound."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_turns: int = Field(ge=1, le=20)
    max_tool_calls: int = Field(ge=0, le=40)
    max_python_runs: int = Field(ge=0, le=10)
    max_output_tokens: int = Field(ge=128, le=4096)
    max_total_tokens: int = Field(ge=1000, le=200000)
    max_result_chars: int = Field(ge=200, le=8000)
    max_claims: int = Field(ge=1, le=50)
    max_hypotheses_examined: int = Field(ge=1, le=2000)
    temperature: float = Field(ge=0, le=1)


class ChatConfig(BaseModel):
    """Hard stops for one chat question and for what chat may test on a dataset."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_turns: int = Field(ge=1, le=12)
    max_tool_calls: int = Field(ge=0, le=20)
    max_output_tokens: int = Field(ge=128, le=4096)
    max_total_tokens: int = Field(ge=1000, le=100000)
    max_result_chars: int = Field(ge=200, le=8000)
    max_question_chars: int = Field(ge=50, le=4000)
    max_answer_chars: int = Field(ge=100, le=4000)
    history_questions: int = Field(ge=0, le=10)
    max_hypotheses_examined: int = Field(ge=1, le=2000)
    max_tests_per_dataset: int = Field(ge=0, le=500)
    max_messages_per_hour: int = Field(ge=1, le=1000)
    temperature: float = Field(ge=0, le=1)


class WorkspaceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sandbox: SandboxConfig
    agent: AgentConfig
    chat: ChatConfig


def load_workspace_config(path: Path | str = DEFAULT_CONFIG_PATH) -> WorkspaceConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return WorkspaceConfig.model_validate(raw["workspace"])
