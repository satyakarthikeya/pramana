"""Structured JSON logging shared by all PRAMANA modules."""

from __future__ import annotations

import logging
from typing import Any, cast

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure stdlib and structlog to emit machine-readable JSON records."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Unknown log level: {level}")

    logging.basicConfig(format="%(message)s", level=numeric_level, force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(**context: Any) -> structlog.stdlib.BoundLogger:
    """Return a structured logger pre-bound to stable contextual fields."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger("pramana").bind(**context))


def bind_run_context(run_id: str, **context: Any) -> None:
    """Bind a run identifier to logs emitted in the current context."""
    structlog.contextvars.bind_contextvars(run_id=run_id, **context)


def clear_log_context() -> None:
    """Clear context-local fields at the end of a workflow run."""
    structlog.contextvars.clear_contextvars()
