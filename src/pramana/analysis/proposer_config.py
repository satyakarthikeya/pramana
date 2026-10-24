"""Explicit DeepSeek-only proposer settings; no local inference or silent fallback."""

from __future__ import annotations

from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProposerSettings(BaseModel):
    """Bound resources and refuse non-DeepSeek models or credential-bearing URLs."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    engine: Literal["deterministic", "api", "agent", "planner"]
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
    # DeepSeek's OpenAI-compatible endpoint, used when engine is "api", "agent" or "planner".
    # The key is read from the environment variable named here, never from config.
    api_base_url: str = "https://api.deepseek.com"
    api_model: str = "deepseek-flash"
    api_key_env: Literal["DEEPSEEK_API_KEY"] = "DEEPSEEK_API_KEY"

    @property
    def active_model(self) -> str:
        """The model name the configured engine will actually call."""
        return self.api_model if self.engine in {"api", "agent", "planner"} else self.model

    @model_validator(mode="after")
    def deepseek_only(self) -> Self:
        """Keys may reach only the official HTTPS API, never a redirect or local model."""
        parsed = urlsplit(self.api_base_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.deepseek.com"
            or parsed.port not in {None, 443}
            or parsed.path not in {"", "/", "/v1", "/v1/"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("analysis requires the official DeepSeek HTTPS endpoint")
        if self.api_model not in {"deepseek-flash", "deepseek-v4-pro"}:
            raise ValueError("analysis requires an explicit supported DeepSeek model")
        if self.engine in {"api", "agent", "planner"} and self.trace_backend != "langfuse":
            raise ValueError("DeepSeek analysis requires Langfuse tracing")
        # Validate retained aliases too: stale Gemma/Ollama settings must fail visibly.
        if self.model not in {"deepseek-flash", "deepseek-v4-pro"}:
            raise ValueError("analysis model alias must name DeepSeek")
        if self.base_url.rstrip("/") not in {
            "https://api.deepseek.com",
            "https://api.deepseek.com/v1",
        }:
            raise ValueError("analysis base_url alias must use the DeepSeek endpoint")
        if self.max_output_tokens >= self.context_tokens:
            raise ValueError("output budget must leave room for the prompt")
        return self
