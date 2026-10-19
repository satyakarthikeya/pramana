"""PASSed insight + proof object -> reusable dataset-agnostic lesson.
Rule-based/templated first; any LLM help uses Gemma and is traced.

Owner: M. Karthik Reddy
Scope: scope/SCOPE_M_Karthik_Reddy.md
"""

from __future__ import annotations

from datetime import UTC, datetime

from pramana.contracts import CandidateInsight, ProofObject
from pramana.memory.fingerprint import DatasetFingerprint
from pramana.memory.lesson import Lesson, lesson_text
from pramana.memory.schema import VerifiedInsightRecord
from pramana.verification.memory_guard import assert_writable


def abstract_lesson(
    candidate: CandidateInsight,
    proof: ProofObject,
    *,
    run_id: str,
    dataset_ref: str,
    fingerprint: DatasetFingerprint,
) -> Lesson:
    """Produce only a historical hint; never generalize its verdict to new data."""
    proof = assert_writable(ProofObject.model_validate(proof.model_dump(mode="python")))
    candidate = CandidateInsight.model_validate(candidate.model_dump(mode="python"))
    return Lesson(
        record_id=VerifiedInsightRecord.record_id_for(run_id, proof.insight_id),
        run_id=run_id,
        dataset_ref=dataset_ref,
        candidate=candidate,
        proof=proof,
        fingerprint=fingerprint,
        text=lesson_text(candidate),
        stored_at=datetime.now(UTC),
    )
