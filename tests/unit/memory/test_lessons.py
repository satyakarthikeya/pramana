"""Real persistent vector-store tests with an explicitly injected test embedding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from pramana.analysis.config import load_config
from pramana.analysis.schema_inference import infer_schema
from pramana.contracts import CandidateInsight, GateOutcome, Verdict
from pramana.memory.abstraction import abstract_lesson
from pramana.memory.config import MemorySettings, load_memory_settings
from pramana.memory.fingerprint import DatasetFingerprint, fingerprint_schema
from pramana.memory.lesson import Lesson
from pramana.memory.store import ChromaLessonStore
from pramana.verification.memory_guard import MemoryWriteRefused
from tests.unit.memory.test_store import _proof


class TestEmbedding:
    """Deterministic two-topic test embedding, never selected by application config."""

    __test__ = False

    def __call__(self, input: list[str]) -> list[Any]:
        return [
            np.array([1.0, 0.0], dtype=np.float32)
            if any(word in text.lower() for word in ("age", "bmi"))
            else np.array([0.0, 1.0], dtype=np.float32)
            for text in input
        ]

    def embed_query(self, input: list[str]) -> list[Any]:
        return self(input)

    @staticmethod
    def name() -> str:
        return "pramana_test_embedding"

    def get_config(self) -> dict[str, Any]:
        return {}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> TestEmbedding:
        return TestEmbedding()


def settings_for(path: Path) -> MemorySettings:
    values = load_memory_settings().model_dump()
    values["chroma"].update(mode="persistent", persist_path=str(path))
    return MemorySettings.model_validate(values)


def fingerprint() -> DatasetFingerprint:
    rng = np.random.default_rng(17)
    frame = pd.DataFrame({"age": rng.normal(45, 10, 100), "bmi": rng.normal(25, 3, 100)})
    schema = infer_schema(frame, load_config().schema_inference)
    return fingerprint_schema(schema)


def candidate(insight_id: str = "ok", ref: str = "cleaned.pkl") -> CandidateInsight:
    return CandidateInsight(
        insight_id=insight_id,
        claim="bmi is associated with age",
        claim_type="correlation",
        variables=["age", "bmi"],
        asserted_direction="positive",
        dataset_ref=ref,
    )


def test_fingerprint_is_value_free_and_order_independent() -> None:
    profile = fingerprint()
    assert profile.columns == {"age": "numeric", "bmi": "numeric"}
    assert "45.0" not in profile.description
    bad = profile.model_dump()
    bad["description"] = "patient record"
    with pytest.raises(ValidationError, match="fingerprint"):
        DatasetFingerprint.model_validate(bad)


def test_abstraction_refuses_rejection_and_mismatched_provenance() -> None:
    with pytest.raises(MemoryWriteRefused):
        abstract_lesson(
            candidate(),
            _proof("ok", GateOutcome.INCONCLUSIVE),
            run_id="run",
            dataset_ref="cleaned.pkl",
            fingerprint=fingerprint(),
        )
    with pytest.raises(ValidationError, match="IDs"):
        abstract_lesson(
            candidate(),
            _proof("different", GateOutcome.SUPPORTED),
            run_id="run",
            dataset_ref="cleaned.pkl",
            fingerprint=fingerprint(),
        )
    lesson = abstract_lesson(
        candidate(),
        _proof("ok", GateOutcome.SUPPORTED),
        run_id="run",
        dataset_ref="cleaned.pkl",
        fingerprint=fingerprint(),
    )
    assert "historical hint" in lesson.text
    assert "new dataset" in lesson.text
    bad = lesson.model_dump(mode="json")
    bad["text"] = "This always holds in every future dataset"
    with pytest.raises(ValidationError, match="text"):
        Lesson.model_validate(bad)


def test_real_chroma_persistence_retry_retrieval_and_rejection(tmp_path: Path) -> None:
    settings = settings_for(tmp_path / "chroma")
    store = ChromaLessonStore(settings, embedding_function=TestEmbedding())
    proof = _proof("ok", GateOutcome.SUPPORTED)
    first = store.write_lessons(
        [candidate()], [proof], run_id="run", dataset_ref="cleaned.pkl", fingerprint=fingerprint()
    )
    assert (
        store.write_lessons(
            [candidate()],
            [proof],
            run_id="run",
            dataset_ref="cleaned.pkl",
            fingerprint=fingerprint(),
        )
        == first
    )
    reopened = ChromaLessonStore(settings, embedding_function=TestEmbedding())
    assert reopened.browse() == first
    hits = reopened.search("age bmi")
    assert hits[0][0] == first[0]
    assert hits[0][1] == pytest.approx(1)
    assert reopened.search("revenue") == []
    assert reopened.search("age bmi", exclude_run_id="run") == []
    with pytest.raises(MemoryWriteRefused):
        store.write_lessons(
            [candidate("other"), candidate("bad")],
            [_proof("other", GateOutcome.SUPPORTED), _proof("bad", GateOutcome.INCONCLUSIVE)],
            run_id="run",
            dataset_ref="cleaned.pkl",
            fingerprint=fingerprint(),
        )
    assert store.browse() == first
    altered = candidate().model_copy(update={"reference_group": "injected"})
    with pytest.raises(ValueError, match="conflicting"):
        store.write_lessons(
            [altered], [proof], run_id="run", dataset_ref="cleaned.pkl", fingerprint=fingerprint()
        )


def test_reject_batch_does_not_even_open_chroma() -> None:
    store = ChromaLessonStore()
    with pytest.raises(MemoryWriteRefused):
        store.write_lessons(
            [candidate()],
            [_proof("ok", GateOutcome.INCONCLUSIVE)],
            run_id="run",
            dataset_ref="cleaned.pkl",
            fingerprint=fingerprint(),
        )
    assert store._collection is None


def test_tampered_persisted_proof_is_never_retrieved(tmp_path: Path) -> None:
    store = ChromaLessonStore(settings_for(tmp_path), embedding_function=TestEmbedding())
    lesson = store.write_lessons(
        [candidate()],
        [_proof("ok", GateOutcome.SUPPORTED)],
        run_id="run",
        dataset_ref="cleaned.pkl",
        fingerprint=fingerprint(),
    )[0]
    payload = lesson.model_dump(mode="json")
    payload["proof"]["verdict"] = Verdict.REJECT.value
    # Deliberately corrupt the backend in this test, bypassing the production boundary.
    store._collection.update(
        ids=[lesson.record_id],
        metadatas=[
            {
                "lesson_json": json.dumps(payload),
                "verdict": "PASS",
                "run_id": "run",
                "insight_id": "ok",
                "fingerprint": lesson.fingerprint.digest,
            }
        ],
    )
    with pytest.raises(ValidationError):
        store.browse()
    with pytest.raises(ValidationError):
        store.search("age bmi")
