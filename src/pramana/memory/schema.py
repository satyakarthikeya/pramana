"""ChromaDB collections + metadata schema for verified lessons:
source insight_id, proof-object metadata, dataset fingerprint, timestamps.

What exists today is the RECORD, not the collection: one stored entry per PASSed
proof object, carrying the full proof plus the fields a reader filters on. The
ChromaDB collection, the embedding and the abstracted lesson text are later build
steps (SCOPE_M 4 steps 1 and 3); this record is what those will be built from.

Claim text is missing from the record on purpose, for now. The memory request
that orchestration sends (`MemoryWriteRequest`) carries proof objects only, and
`ProofObject` has no claim field, so memory has no claim text to store. That is
an interface gap to agree with orchestration, not something to reconstruct here.

Owner: M. Karthik Reddy
Scope: scope/SCOPE_M_Karthik_Reddy.md
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pramana.contracts import EffectMetric, GateOutcome, ProofObject, Verdict


class VerifiedInsightRecord(BaseModel):
    """One PASSed proof object as it is stored.

    Guarantees: `verdict` is PASS and `gate_outcome` is SUPPORTED by construction,
    since `from_proof` is only ever called on a proof the memory guard admitted;
    the literal types make any other value a validation error even if it is not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    dataset_ref: str | None
    insight_id: str = Field(min_length=1)
    verdict: Literal[Verdict.PASS]
    gate_outcome: Literal[GateOutcome.SUPPORTED]
    q_value: float | None
    effect_size: float | None
    effect_metric: EffectMetric | None
    evidence_score: float | None
    bh_family_id: str
    stored_at: datetime
    proof: dict[str, Any]

    @staticmethod
    def record_id_for(run_id: str, insight_id: str) -> str:
        """Stable id: re-writing the same run's proof names the same record."""
        return hashlib.sha256(f"{run_id}\x1f{insight_id}".encode()).hexdigest()[:24]

    @classmethod
    def from_proof(
        cls,
        proof: ProofObject,
        *,
        run_id: str,
        dataset_ref: str | None,
        stored_at: datetime,
    ) -> VerifiedInsightRecord:
        """Project a guard-admitted proof object into its stored form."""
        return cls(
            record_id=cls.record_id_for(run_id, proof.insight_id),
            run_id=run_id,
            dataset_ref=dataset_ref,
            insight_id=proof.insight_id,
            verdict=proof.verdict,  # type: ignore[arg-type]
            gate_outcome=proof.gate_outcome,  # type: ignore[arg-type]
            q_value=proof.q_value,
            effect_size=proof.effect_size,
            effect_metric=proof.effect_metric,
            evidence_score=proof.evidence_score,
            bh_family_id=proof.bh_family_id,
            stored_at=stored_at,
            proof=proof.model_dump(mode="json"),
        )
