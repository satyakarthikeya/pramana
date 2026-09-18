"""Celery/Redis queue plumbing for verification-owned execution internals."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pandas as pd
from celery import Celery, signals

from pramana.common.config import load_runtime_config
from pramana.common.logging import (
    bind_run_context,
    clear_log_context,
    configure_logging,
    get_logger,
)
from pramana.common.paths import DATA_DIR
from pramana.contracts import CandidateInsight, ProofObject
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


def validate_worker_timeouts() -> None:
    """Refuse a worker whose Celery soft limit cannot cover executor cleanup."""
    from pramana.verification.config import load_config as load_verification_config

    verification = load_verification_config()
    if _runtime.queue.task_soft_time_limit <= verification.executor.timeout_seconds:
        raise RuntimeError(
            "Celery task_soft_time_limit must exceed verification executor timeout_seconds"
        )


@signals.setup_logging.connect  # type: ignore[untyped-decorator]
def configure_worker_logging(**_kwargs: Any) -> None:
    """Apply the project JSON logger when Celery initializes worker logging."""
    configure_logging(_runtime.logging.level)


@signals.worker_init.connect  # type: ignore[untyped-decorator]
def validate_worker_configuration(**_kwargs: Any) -> None:
    """Validate cross-module worker limits before accepting verification tasks."""
    validate_worker_timeouts()


def register_verification_handler(handler: VerificationHandler) -> None:
    """Register the verification team's adapter in the current worker process."""
    global _handler
    _handler = handler


def native_verification_handler(
    request: Mapping[str, Any],
    *,
    data_dir: Path | None = None,
) -> Mapping[str, Any]:
    """Call the verification gateway on the exact cleaned artifact for this run."""
    from pramana.verification.config import load_config as load_verification_config
    from pramana.verification.gateway import verify_batch

    run_id = UUID(str(request.get("run_id", "")))
    artifact_root = (data_dir or DATA_DIR).resolve()
    expected_path = artifact_root / "runs" / str(run_id) / "cleaned.pkl"
    supplied_path = Path(str(request.get("dataset_ref", ""))).resolve()
    if supplied_path != expected_path.resolve():
        raise ValueError("Verification may only read the cleaned artifact produced for this run")
    if not supplied_path.is_file():
        raise FileNotFoundError(f"Cleaned dataset does not exist: {supplied_path}")

    frame = pd.read_pickle(supplied_path)
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Cleaned dataset artifact must contain a pandas DataFrame")
    raw_candidates = request.get("candidate_insights")
    if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, (str, bytes)):
        raise TypeError("candidate_insights must be a sequence")
    candidates = [
        item if isinstance(item, CandidateInsight) else CandidateInsight.model_validate(item)
        for item in raw_candidates
    ]
    mismatched = [
        candidate.insight_id
        for candidate in candidates
        if Path(candidate.dataset_ref).resolve() != supplied_path
    ]
    if mismatched:
        raise ValueError(
            "Verification candidates must reference the exact cleaned artifact; "
            f"mismatched insight IDs: {mismatched}"
        )
    proofs = verify_batch(candidates, frame, load_verification_config())
    return {"proof_objects": proofs}


def _load_configured_handler() -> VerificationHandler:
    """Load a package-scoped override or use the native verification gateway."""
    global _handler
    if _handler is not None:
        return _handler

    import_path = os.getenv("PRAMANA_VERIFICATION_HANDLER", "")
    if not import_path:
        return native_verification_handler
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


@celery_app.task(bind=True, name="pramana.verify_batch", acks_late=False)  # type: ignore[untyped-decorator]
def verify_batch_task(
    self: Any,
    run_id: str,
    candidates: Sequence[Mapping[str, Any]],
    dataset_ref: str,
) -> Mapping[str, Any]:
    """Dispatch one complete candidate family and propagate failures unchanged."""
    bind_run_context(run_id, task_id=self.request.id)
    validated_candidates = [
        item if isinstance(item, CandidateInsight) else CandidateInsight.model_validate(item)
        for item in candidates
    ]
    mismatched = [
        candidate.insight_id
        for candidate in validated_candidates
        if candidate.dataset_ref != dataset_ref
    ]
    if mismatched:
        raise ValueError(
            "Verification candidates must reference the queued cleaned dataset; "
            f"mismatched insight IDs: {mismatched}"
        )
    request = {
        "run_id": run_id,
        "candidate_insights": [
            candidate.model_dump(mode="json") for candidate in validated_candidates
        ],
        "dataset_ref": dataset_ref,
    }
    get_logger(component="celery", run_id=run_id).info(
        "verification_dispatched", n_candidates=len(candidates)
    )
    try:
        result = _load_configured_handler()(request)
        if not isinstance(result, Mapping) or "proof_objects" not in result:
            raise ValueError("Verification handler must return a mapping containing proof_objects")
        proofs = [
            item if isinstance(item, ProofObject) else ProofObject.model_validate(item)
            for item in result["proof_objects"]
        ]
        candidate_ids = [candidate.insight_id for candidate in validated_candidates]
        proof_ids = [proof.insight_id for proof in proofs]
        if proof_ids != candidate_ids:
            raise ValueError(
                "Verification must return exactly one proof per candidate in input order"
            )
        return {"proof_objects": [proof.model_dump(mode="json") for proof in proofs]}
    finally:
        clear_log_context()


def enqueue_verification(
    run_id: str,
    candidates: Sequence[Mapping[str, Any]],
    dataset_ref: str,
) -> Any:
    """Queue a complete hypothesis family as one task so BH-FDR remains batch-wide."""
    return verify_batch_task.apply_async(args=(run_id, list(candidates), dataset_ref))
