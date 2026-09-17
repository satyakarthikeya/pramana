"""Run creation, valid transitions, retries, and fail-closed degradation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pramana.common.config import RuntimeConfig, load_runtime_config
from pramana.orchestration.state import PramanaState, RunError, RunStatus

_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.PENDING: {RunStatus.RUNNING, RunStatus.FAILED},
    RunStatus.RUNNING: {RunStatus.COMPLETED, RunStatus.DEGRADED, RunStatus.FAILED},
    RunStatus.DEGRADED: {RunStatus.FAILED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
}


def new_run(
    dataset_ref: str | None = None,
    runtime: RuntimeConfig | None = None,
    *,
    user_query: str | None = None,
) -> PramanaState:
    """Create a pending run with a unique ID and validated runtime configuration."""
    return PramanaState(
        run_id=uuid4(),
        dataset_ref=dataset_ref,
        user_query=user_query,
        runtime=runtime or load_runtime_config(),
    )


def state_copy(state: PramanaState, update: Mapping[str, Any]) -> PramanaState:
    """Return a fully revalidated Pydantic v2 state copy."""
    values = {**state.__dict__, **dict(update)}
    return PramanaState.model_validate(values)


def transition(state: PramanaState, target: RunStatus) -> PramanaState:
    """Move a run to ``target`` only when the lifecycle permits it."""
    if target == state.status:
        return state
    if target not in _TRANSITIONS[state.status]:
        raise ValueError(f"Invalid run transition: {state.status.value} -> {target.value}")
    return state_copy(state, {"status": target})


def start_run(state: PramanaState) -> PramanaState:
    """Move a newly-created run into its executing state."""
    running = transition(state, RunStatus.RUNNING)
    started_at = datetime.now(UTC)
    return state_copy(
        running,
        {
            "started_at": started_at,
            "deadline_at": started_at + timedelta(seconds=state.runtime.run.graph_timeout_seconds),
        },
    )


def record_failure(
    state: PramanaState,
    node: str,
    error: Exception,
    attempt: int,
    *,
    exhausted: bool,
) -> PramanaState:
    """Record a node failure and degrade the run once retries are exhausted."""
    errors = [
        *state.errors,
        RunError(
            node=node,
            error_type=type(error).__name__,
            message=str(error),
            attempt=attempt,
        ),
    ]
    retries = {**state.retry_counts, node: attempt - 1}
    status = RunStatus.DEGRADED if exhausted else state.status
    return state_copy(state, {"errors": errors, "retry_counts": retries, "status": status})


def complete_run(state: PramanaState) -> PramanaState:
    """Complete a healthy run while preserving degraded runs as degraded."""
    if state.status == RunStatus.DEGRADED:
        return state
    return transition(state, RunStatus.COMPLETED)
