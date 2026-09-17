"""Lazy Langfuse client construction and run-context helpers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pramana.common.config import LangfuseSettings
from pramana.common.logging import get_logger

_client: Any | None = None


def get_langfuse_client(settings: LangfuseSettings) -> Any | None:
    """Return a shared client, or ``None`` when tracing is disabled or unconfigured."""
    global _client
    if not settings.enabled:
        return None
    required = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
    if any(not os.getenv(name) for name in required):
        get_logger(component="langfuse").warning("langfuse_disabled_missing_credentials")
        return None
    if _client is None:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.environ["LANGFUSE_HOST"],
        )
    return _client


@contextmanager
def traced_run(client: Any | None, run_id: str, name: str = "pramana-run") -> Iterator[Any]:
    """Yield a run trace when supported while remaining a no-op when disabled."""
    if client is None:
        yield None
        return

    observation_factory = getattr(client, "start_as_current_observation", None)
    if observation_factory is not None:
        trace_id = run_id.replace("-", "")
        with observation_factory(
            trace_context={"trace_id": trace_id},
            name=name,
            as_type="agent",
            metadata={"run_id": run_id},
        ) as observation:
            yield observation
        return

    trace_factory = getattr(client, "trace", None)
    if trace_factory is not None:
        yield trace_factory(id=run_id, name=name)
        return

    get_logger(component="langfuse", run_id=run_id).warning("trace_api_unavailable")
    yield None
