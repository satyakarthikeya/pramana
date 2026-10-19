"""Validated CPU-friendly local proposer settings, separate from inference settings."""

from __future__ import annotations

from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProposerSettings(BaseModel):
    """Bound model resources and refuse remote endpoints or verification-tier models."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    engine: Literal["deterministic", "ollama"]
    trace_backend: Literal["local", "langfuse"]
    model: str
    base_url: str
    timeout_seconds: int = Field(gt=0, le=600)
    seed: int = Field(ge=0)
    temperature: float = Field(ge=0, le=1)
    max_claims: int = Field(ge=1, le=50)
    max_columns: int = Field(ge=2, le=50)
    max_levels: int = Field(ge=2, le=20)
    max_prompt_chars: int = Field(ge=1000, le=20000)
    max_question_chars: int = Field(ge=1, le=2000)
    max_hint_chars: int = Field(ge=1, le=4000)
    max_output_tokens: int = Field(ge=128, le=4096)
    context_tokens: int = Field(ge=2048, le=8192)
    num_threads: int = Field(ge=1, le=16)

    @model_validator(mode="after")
    def local_gemma_only(self) -> Self:
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname
            not in {"localhost", "127.0.0.1", "::1", "ollama", "host.docker.internal"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("analysis proposer requires an explicit local Ollama endpoint")
        if not self.model.startswith("gemma") or ":" not in self.model or "cloud" in self.model:
            raise ValueError("this local proposer requires an explicit Gemma model tag")
        if self.max_output_tokens >= self.context_tokens:
            raise ValueError("output budget must leave room for the prompt")
        return self
