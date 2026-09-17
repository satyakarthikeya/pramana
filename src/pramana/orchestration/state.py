"""The single Pydantic state object flowing through the PRAMANA graph."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pramana.common.config import RuntimeConfig
from pramana.contracts import CandidateInsight, ProofObject


class RunStatus(StrEnum):
    """Lifecycle states for a single graph execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"


class RunError(BaseModel):
    """Serializable failure information retained in the graph state."""

    node: str
    error_type: str
    message: str
    attempt: int = Field(ge=1)


class PramanaState(BaseModel):
    """Carry one run through every node without duplicating module contracts."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        validate_assignment=True,
    )

    run_id: UUID
    status: RunStatus = RunStatus.PENDING
    runtime: RuntimeConfig
    started_at: datetime | None = None
    deadline_at: datetime | None = None
    dataset_ref: str | None = None
    dataset: Any = None
    schema_profile: dict[str, Any] = Field(default_factory=dict)
    candidate_insights: list[CandidateInsight] = Field(default_factory=list)
    proof_objects: list[ProofObject] = Field(default_factory=list)
    memory_receipts: list[Any] = Field(default_factory=list)
    report: dict[str, Any] | None = None
    retry_counts: dict[str, int] = Field(default_factory=dict)
    errors: list[RunError] = Field(default_factory=list)
    visited_nodes: list[str] = Field(default_factory=list)
