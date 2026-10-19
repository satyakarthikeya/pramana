"""Episode-mode retrieval: new dataset fingerprint -> relevant verified lessons.
Returns verified lessons only, each traceable to its insight_id.

Owner: M. Karthik Reddy
Scope: scope/SCOPE_M_Karthik_Reddy.md
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pramana.memory.fingerprint import DatasetFingerprint
from pramana.memory.lesson import Lesson
from pramana.memory.store import ChromaLessonStore


class RetrievedLesson(BaseModel):
    """A previous verified lesson, explicitly labelled as a hint for a new run."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    lesson: Lesson
    similarity: float = Field(ge=-1, le=1)


def retrieve_lessons(
    store: ChromaLessonStore,
    fingerprint: DatasetFingerprint,
    *,
    exclude_run_id: str | None = None,
) -> list[RetrievedLesson]:
    """Return source-verified hints; new claims still require independent verification."""
    return [
        RetrievedLesson(lesson=lesson, similarity=similarity)
        for lesson, similarity in store.search(
            fingerprint.description, exclude_run_id=exclude_run_id
        )
    ]
