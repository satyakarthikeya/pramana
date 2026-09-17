"""Celery/Redis queue plumbing for verification-owned execution internals."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from celery import Celery

from pramana.common.config import load_runtime_config
from pramana.common.logging import bind_run_context, get_logger
from pramana.orchestration.adapters import IntegrationDependencyError

VerificationHandler = Callable[[Mapping[str, Any]], Mapping[str, Any]]
_handler: VerificationHandler | None = None
_runtime = load_runtime_config()

celery_app = Celery(
    "pramana",
    broker=_runtime.queue.broker_url,
    backend=_runtime.queue.result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_soft_time_limit=_runtime.queue.task_soft_time_limit,
    task_time_limit=_runtime.queue.task_hard_time_limit,
    worker_prefetch_multiplier=1,
)


def register_verification_handler(handler: VerificationHandler) -> None:
    """Register the verification team's adapter in the current worker process."""
    global _handler
    _handler = handler


def _load_configured_handler() -> VerificationHandler:
    """Load only an explicitly configured function inside ``pramana.verification``."""
    global _handler
    if _handler is not None:
        return _handler

    import_path = os.getenv("PRAMANA_VERIFICATION_HANDLER", "")
    if not import_path:
        raise IntegrationDependencyError("PRAMANA_VERIFICATION_HANDLER is not configured")
    module_name, separator, attribute = import_path.partition(":")
    if not separator or not module_name.startswith("pramana.verification."):
        raise IntegrationDependencyError(
            "Verification handler must use pramana.verification.<module>:<function>"
        )
    candidate = getattr(importlib.import_module(module_name), attribute, None)
    if not callable(candidate):
        raise IntegrationDependencyError(f"Verification handler is not callable: {import_path}")
    _handler = cast(VerificationHandler, candidate)
    return _handler


@celery_app.task(bind=True, name="pramana.verify_batch", acks_late=True)  # type: ignore[untyped-decorator]
def verify_batch_task(
    self: Any,
    run_id: str,
    candidates: Sequence[Mapping[str, Any]],
    dataset_ref: str,
) -> Mapping[str, Any]:
    """Dispatch one complete candidate family and propagate failures unchanged."""
    bind_run_context(run_id, task_id=self.request.id)
    request = {
        "run_id": run_id,
        "candidate_insights": list(candidates),
        "dataset_ref": dataset_ref,
    }
    get_logger(component="celery", run_id=run_id).info(
        "verification_dispatched", n_candidates=len(candidates)
    )
    result = _load_configured_handler()(request)
    if not isinstance(result, Mapping) or "proof_objects" not in result:
        raise ValueError("Verification handler must return a mapping containing proof_objects")
    return result


def enqueue_verification(
    run_id: str,
    candidates: Sequence[Mapping[str, Any]],
    dataset_ref: str,
) -> Any:
    """Queue a complete hypothesis family as one task so BH-FDR remains batch-wide."""
    return verify_batch_task.apply_async(args=(run_id, list(candidates), dataset_ref))
