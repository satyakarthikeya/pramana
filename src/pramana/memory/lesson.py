"""Pydantic Lesson model. Proof-object schema is imported, not redefined.

Owner: M. Karthik Reddy
Scope: scope/SCOPE_M_Karthik_Reddy.md
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pramana.contracts import CandidateInsight, ProofObject
from pramana.memory.fingerprint import DatasetFingerprint
from pramana.memory.schema import VerifiedInsightRecord
from pramana.verification.memory_guard import assert_writable


def lesson_text(candidate: CandidateInsight) -> str:
    """Render structured fields as a historical hint without model-authored claims."""
    variables = ", ".join(candidate.variables)
    direction = candidate.asserted_direction.value if candidate.asserted_direction else "undirected"
    group = f"; reference group {candidate.reference_group}" if candidate.reference_group else ""
    return (
        f"In a previous dataset, verification supported a {direction} "
        f"{candidate.claim_type.value} involving {variables}{group}. "
        "Consider testing this pattern under comparable conditions. "
        "This is a historical hint, not evidence or a verified finding about a new dataset."
    )


class Lesson(BaseModel):
    """Admit only a matching candidate, PASS proof, dataset and schema provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    record_id: str
    run_id: str = Field(min_length=1)
    dataset_ref: str = Field(min_length=1)
    candidate: CandidateInsight
    proof: ProofObject
    fingerprint: DatasetFingerprint
    text: str
    stored_at: datetime

    @model_validator(mode="after")
    def verified_provenance(self) -> Lesson:
        proof = ProofObject.model_validate(self.proof.model_dump(mode="python"))
        assert_writable(proof)
        if self.candidate.insight_id != proof.insight_id:
            raise ValueError("candidate and proof insight IDs do not match")
        if self.candidate.dataset_ref != self.dataset_ref:
            raise ValueError("candidate does not reference the verified dataset")
        if not set(self.candidate.variables) <= set(self.fingerprint.columns):
            raise ValueError("candidate variables missing from source fingerprint")
        if self.record_id != VerifiedInsightRecord.record_id_for(self.run_id, proof.insight_id):
            raise ValueError("lesson record ID does not match provenance")
        if self.text != lesson_text(self.candidate):
            raise ValueError("lesson text does not match its structured candidate")
        if self.stored_at.tzinfo is None:
            raise ValueError("lesson timestamp must include timezone")
        return self
