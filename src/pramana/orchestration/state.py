"""The single Pydantic state object flowing through the PRAMANA graph."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pramana.common.config import RuntimeConfig
from pramana.contracts import CandidateInsight, DataStructure, ProofObject
from pramana.verification.gateway import BatchSummary


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
    user_query: str | None = None
    episode_mode: bool = False
    lesson_hints: list[str] = Field(default_factory=list)
    retrieved_lessons: list[dict[str, Any]] = Field(default_factory=list)
    dataset: Any = None
    dataset_metadata: dict[str, Any] = Field(default_factory=dict)
    cleaning_report: dict[str, Any] = Field(default_factory=dict)
    dataset_profile: dict[str, Any] = Field(default_factory=dict)
    schema_profile: dict[str, Any] = Field(default_factory=dict)
    data_structure: DataStructure | None = Field(
        default=None,
        description="How the rows depend on each other, classified in preparation. The "
        "proposer sees only the exploration split and the gate only the confirmation "
        "split (PLAN D5).",
    )
    candidate_insights: list[CandidateInsight] = Field(default_factory=list)
    exploration: dict[str, Any] | None = None
    proof_objects: list[ProofObject] = Field(default_factory=list)
    verification_summary: BatchSummary | None = None
    memory_receipts: list[Any] = Field(default_factory=list)
    report: dict[str, Any] | None = None
    retry_counts: dict[str, int] = Field(default_factory=dict)
    errors: list[RunError] = Field(default_factory=list)
    visited_nodes: list[str] = Field(default_factory=list)
