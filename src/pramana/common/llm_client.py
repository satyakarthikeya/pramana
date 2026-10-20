"""Bounded OpenAI-compatible inference transport; models never decide statistics.

This additive W4 interface is available to module owners without replacing their
existing clients. Only successful, run-linked Langfuse tracing permits a request.
Provider/model selection is explicit and never changes on a retry.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from pramana.common.config import LangfuseSettings
from pramana.common.langfuse_client import get_langfuse_client
from pramana.common.logging import get_logger


class LLMUnavailable(RuntimeError):
    """Inference or required tracing failed; callers must not substitute a model."""


class _TransportFailure(Exception):
    def __init__(self, retryable: bool) -> None:
        self.retryable = retryable


class ChatMessage(BaseModel):
    """One explicit text-only chat message, never credentials or raw dataset rows."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class LLMSettings(BaseModel):
    """Transport budgets and optional caller-supplied prices, not statistical policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    base_url: str
    model: str = Field(min_length=1)
    api_key: SecretStr = Field(repr=False)
    timeout_seconds: float = Field(default=30, gt=0, le=600)
    max_retries: int = Field(default=2, ge=0, le=5)
    retry_delay_seconds: float = Field(default=1, ge=0, le=10)
    max_response_bytes: int = Field(default=1048576, ge=1024, le=10485760)
    input_usd_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_usd_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def safe_endpoint(self) -> LLMSettings:
        """Refuse URL credentials and plaintext remote endpoints before sending keys."""
        url = urlsplit(self.base_url)
        local = url.hostname in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
        if (
            not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or (url.scheme != "https" and not (url.scheme == "http" and local))
        ):
            raise ValueError("Use HTTPS or a local HTTP endpoint, without URL credentials")
        if not self.api_key.get_secret_value().strip():
            raise ValueError("An explicit key is required; use a local placeholder for Ollama")
        if (self.input_usd_per_million is None) != (self.output_usd_per_million is None):
            raise ValueError("Configure both token prices or neither")
        return self


class Completion(BaseModel):
    """Raw model text and measured usage, never verification evidence or a verdict."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    content: str = Field(min_length=1)
    returned_model: str | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        # Never forward an Authorization header to a redirect's destination.
        return None


def _request(settings: LLMSettings, payload: bytes) -> dict[str, Any]:
    request = Request(
        settings.base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + settings.api_key.get_secret_value(),
        },
        method="POST",
    )
    with build_opener(_NoRedirect()).open(request, timeout=settings.timeout_seconds) as response:
        raw = response.read(settings.max_response_bytes + 1)
    if len(raw) > settings.max_response_bytes:
        raise LLMUnavailable("Model response exceeded the configured byte limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise LLMUnavailable("Model response must be a JSON object")
    return value


def _completion(value: dict[str, Any], settings: LLMSettings) -> Completion:
    choices = value.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMUnavailable("Model returned no completion")
    choice = choices[0]
    if choice.get("finish_reason") not in {"stop", None}:
        raise LLMUnavailable("Model response was truncated or refused")
    text = choice["message"]["content"]
    if not isinstance(text, str) or not text.strip():
        raise LLMUnavailable("Model returned empty or non-text content")
    usage = value.get("usage") or {}
    tokens_in, tokens_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
    cost = None
    if (
        tokens_in is not None
        and tokens_out is not None
        and settings.input_usd_per_million is not None
        and settings.output_usd_per_million is not None
    ):
        cost = (
            tokens_in * settings.input_usd_per_million
            + tokens_out * settings.output_usd_per_million
        ) / 1000000
    return Completion(
        content=text,
        returned_model=value.get("model"),
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        estimated_cost_usd=cost,
    )


def complete_chat(
    settings: LLMSettings,
    messages: Sequence[ChatMessage],
    *,
    run_id: UUID,
    insight_id: str | None = None,
    temperature: float = 0,
    max_tokens: int = 2048,
) -> Completion:
    """Return traced text with bounded same-model retries, or fail without fallback.

    Cost is an estimate only when the caller provides both prices and the server
    returns token usage. Unknown cost is None, never a fabricated zero. No prompt,
    response, API key or provider exception text is written to application logs.
    """
    if not isinstance(run_id, UUID) or not messages or not 0 <= temperature <= 2:
        raise ValueError("A run UUID, messages and a temperature in [0, 2] are required")
    if not 1 <= max_tokens <= 131072:
        raise ValueError("max_tokens must be between 1 and 131072")
    try:
        client = get_langfuse_client(LangfuseSettings(enabled=True))
        if client is None or not client.auth_check():
            raise LLMUnavailable("Langfuse authentication failed")
    except Exception:
        raise LLMUnavailable("Langfuse authentication is required before inference") from None
    observe = getattr(client, "start_as_current_observation", None)
    if observe is None:
        raise LLMUnavailable("Configured Langfuse tracing is required before inference")
    payload = json.dumps(
        {
            "model": settings.model,
            "messages": [item.model_dump() for item in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
    ).encode("utf-8")
    logger = get_logger(component="llm", run_id=str(run_id), insight_id=insight_id)
    for attempt in range(settings.max_retries + 1):
        try:
            with observe(
                name="llm-completion",
                as_type="generation",
                trace_context={"trace_id": run_id.hex},
                model=settings.model,
                model_parameters={"temperature": temperature, "max_tokens": max_tokens},
                metadata={"run_id": str(run_id), "insight_id": insight_id, "attempt": attempt + 1},
                input=[item.model_dump() for item in messages],
            ) as span:
                try:
                    value = _request(settings, payload)
                except (HTTPError, URLError, TimeoutError) as error:
                    retryable = (
                        not isinstance(error, HTTPError)
                        or error.code in {408, 429}
                        or error.code >= 500
                    )
                    if isinstance(error, HTTPError):
                        error.close()
                    raise _TransportFailure(retryable) from None
                result = _completion(value, settings)
                usage = {
                    key: count
                    for key, count in {
                        "input": result.input_tokens,
                        "output": result.output_tokens,
                    }.items()
                    if count is not None
                }
                span.update(
                    output=result.content,
                    usage_details=usage,
                    cost_details=(
                        {"total": result.estimated_cost_usd}
                        if result.estimated_cost_usd is not None
                        else {}
                    ),
                )
            logger.info(
                "llm_completed",
                model=settings.model,
                attempt=attempt + 1,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                estimated_cost_usd=result.estimated_cost_usd,
            )
            return result
        except _TransportFailure as error:
            logger.warning(
                "llm_request_failed",
                attempt=attempt + 1,
                retryable=error.retryable,
            )
            if not error.retryable or attempt == settings.max_retries:
                raise LLMUnavailable(
                    "Model request failed; no provider/model substitution"
                ) from None
            time.sleep(min(settings.retry_delay_seconds * 2**attempt, 10))
        except Exception:
            raise LLMUnavailable("Model response or required tracing failed") from None
    raise AssertionError("Unreachable retry loop")
