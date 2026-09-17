"""Validated configuration loading for project-owned YAML files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pramana.common.paths import config_path

ModelT = TypeVar("ModelT", bound=BaseModel)


class StrictSettings(BaseModel):
    """Reject unknown configuration keys and prevent mutation after validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RunSettings(StrictSettings):
    """Graph-level retry and timeout settings for one workflow run."""

    graph_timeout_seconds: int = Field(gt=0)
    max_node_retries: int = Field(ge=0)
    on_exhausted_retries: Literal["degrade"]


class QueueSettings(StrictSettings):
    """Celery broker/backend locations and task time limit."""

    broker_url: str = Field(min_length=1)
    result_backend: str = Field(min_length=1)
    task_soft_time_limit: int = Field(gt=0)
    task_hard_time_limit: int = Field(gt=0)
    result_timeout_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_timeout_order(self) -> QueueSettings:
        """Guarantee the caller waits long enough for worker-side termination."""
        if self.task_hard_time_limit <= self.task_soft_time_limit:
            raise ValueError("task_hard_time_limit must exceed task_soft_time_limit")
        if self.result_timeout_seconds < self.task_hard_time_limit:
            raise ValueError("result_timeout_seconds must cover task_hard_time_limit")
        return self


class LangfuseSettings(StrictSettings):
    """Project-wide tracing switch; credentials always come from the environment."""

    enabled: bool


class LoggingSettings(StrictSettings):
    """Structured logging settings."""

    level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]
    format: Literal["json"]


class RuntimeConfig(StrictSettings):
    """Validated contents of ``configs/runtime.yaml``."""

    run: RunSettings
    queue: QueueSettings
    langfuse: LangfuseSettings
    logging: LoggingSettings

    @model_validator(mode="after")
    def validate_graph_deadline(self) -> RuntimeConfig:
        """Ensure all configured crash retries fit inside the graph deadline."""
        required = self.queue.result_timeout_seconds * (self.run.max_node_retries + 1)
        if self.run.graph_timeout_seconds < required:
            raise ValueError(
                "graph_timeout_seconds must cover every configured verification attempt"
            )
        return self


def load_yaml(name: str) -> dict[str, Any]:
    """Load a project config mapping without resolving secrets."""
    path = config_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file does not exist: {path}")
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"Configuration root must be a mapping: {path}")
    return loaded


def load_config(name: str, model: type[ModelT]) -> ModelT:
    """Load and validate a named project configuration with ``model``."""
    return model.model_validate(load_yaml(name))


def load_runtime_config() -> RuntimeConfig:
    """Return runtime settings with supported environment overrides applied."""
    values = load_yaml("runtime")
    queue = values.setdefault("queue", {})
    logging_values = values.setdefault("logging", {})
    langfuse = values.setdefault("langfuse", {})

    if broker_url := os.getenv("REDIS_URL"):
        queue["broker_url"] = broker_url
    if result_backend := os.getenv("CELERY_RESULT_BACKEND"):
        queue["result_backend"] = result_backend
    if log_level := os.getenv("PRAMANA_LOG_LEVEL"):
        logging_values["level"] = log_level.upper()
    if enabled := os.getenv("PRAMANA_LANGFUSE_ENABLED"):
        langfuse["enabled"] = enabled.strip().lower() in {"1", "true", "yes", "on"}

    return RuntimeConfig.model_validate(values)


def load_config_file(path: Path, model: type[ModelT]) -> ModelT:
    """Validate an explicit YAML file, primarily for isolated tests and tooling."""
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"Configuration root must be a mapping: {path}")
    return model.model_validate(loaded)
