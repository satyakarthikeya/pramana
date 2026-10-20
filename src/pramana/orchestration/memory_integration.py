"""Thin graph adapters for the memory owner's guarded store and retrieval API."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from pramana.contracts import ProofObject
from pramana.orchestration.state import PramanaState

if TYPE_CHECKING:
    from pramana.memory.store import ChromaLessonStore


class MemoryIntegration:
    """Share one lazily connected store between retrieval and guarded writes."""

    def __init__(self, store: ChromaLessonStore | None = None) -> None:
        self._store = store

    @property
    def store(self) -> ChromaLessonStore:
        """Construct the configured backend without substituting temporary storage."""
        if self._store is None:
            from pramana.memory.store import ChromaLessonStore

            self._store = ChromaLessonStore()
        return self._store

    def retrieve(self, state: PramanaState) -> dict[str, Any]:
        """Retrieve source-verified historical hints, never new proofs or candidates."""
        from pramana.analysis.schema_inference import SchemaProfile
        from pramana.memory.fingerprint import fingerprint_schema
        from pramana.memory.retrieval import RetrievedLesson, retrieve_lessons

        schema = SchemaProfile.model_validate(state.schema_profile)
        # Empty/unusable datasets cannot have relevant schema-based lessons.
        if not any(column.usable_for_hypotheses for column in schema.columns.values()):
            return {"lesson_hints": [], "retrieved_lessons": []}
        retrieved = retrieve_lessons(
            self.store, fingerprint_schema(schema), exclude_run_id=str(state.run_id)
        )
        validated = [
            RetrievedLesson.model_validate(item.model_dump(mode="python")) for item in retrieved
        ]
        if any(item.lesson.run_id == str(state.run_id) for item in validated):
            raise ValueError("Episode hints must come from a previous run")
        return {
            "lesson_hints": [item.lesson.text for item in validated],
            "retrieved_lessons": [item.model_dump(mode="json") for item in validated],
        }

    def write(
        self, state: PramanaState, proofs: Sequence[ProofObject]
    ) -> dict[str, Any]:
        """Pass original candidates, schema and proofs to the memory-owned guard."""
        from pramana.analysis.schema_inference import SchemaProfile
        from pramana.memory.fingerprint import fingerprint_schema

        if not proofs:
            return {"memory_receipts": []}
        if not state.dataset_ref:
            raise ValueError("Memory requires the exact cleaned dataset reference")
        lessons = self.store.write_lessons(
            state.candidate_insights,
            proofs,
            run_id=str(state.run_id),
            dataset_ref=state.dataset_ref,
            fingerprint=fingerprint_schema(SchemaProfile.model_validate(state.schema_profile)),
        )
        return {
            "memory_receipts": [
                {
                    "record_id": lesson.record_id,
                    "insight_id": lesson.proof.insight_id,
                    "backend": "chromadb",
                }
                for lesson in lessons
            ]
        }
