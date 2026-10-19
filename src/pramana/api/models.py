"""API-owned payloads reuse the authoritative candidate and proof contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pramana.contracts import ProofObject, Verdict
from pramana.orchestration.state import RunStatus


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunView(Payload):
    run_id: UUID
    status: RunStatus
    file_name: str
    created_at: datetime
    finished_at: datetime | None = None
    error: str | None = None


class ResultRow(Payload):
    insight_id: str
    claim: str
    proof: ProofObject


class RunResults(Payload):
    run: RunView
    verified_insights: list[ResultRow]
    rejected_claims: list[ResultRow]
    candidate_count: int = Field(ge=0)
    unverified_candidate_count: int = Field(ge=0)

    @model_validator(mode="after")
    def separate_findings_and_rejections(self) -> RunResults:
        rows = self.verified_insights + self.rejected_claims
        if any(row.proof.verdict is not Verdict.PASS for row in self.verified_insights):
            raise ValueError("a verified finding must have a PASS proof")
        if any(row.proof.verdict is not Verdict.REJECT for row in self.rejected_claims):
            raise ValueError("a rejected claim must have a REJECT proof")
        if any(row.insight_id != row.proof.insight_id for row in rows):
            raise ValueError("result and proof IDs do not match")
        if len({row.insight_id for row in rows}) != len(rows):
            raise ValueError("duplicate result IDs")
        if len(rows) + self.unverified_candidate_count != self.candidate_count:
            raise ValueError("candidate/proof counts do not match")
        return self


class MemorySearch(Payload):
    query: str = Field(min_length=1, max_length=10000)
    top_k: int = Field(default=5, ge=1, le=100)
