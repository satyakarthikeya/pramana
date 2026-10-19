"""The single write path. Wraps verification.memory_guard before any write.

No other file in this repo may import chromadb -- there is a test that greps
for it and fails the build (SCOPE_M 4 step 2).

The original proof-only handler uses a temporary JSONL backend under ignored
artifacts/. ChromaLessonStore below is the contextual, persistent vector backend
used by the API. It requires candidate and schema provenance and never falls back
to the legacy backend when embeddings or Chroma are unavailable.

Owner: M. Karthik Reddy
Scope: scope/SCOPE_M_Karthik_Reddy.md
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pramana.common.paths import ARTIFACTS_DIR
from pramana.contracts import ProofObject
from pramana.memory.schema import VerifiedInsightRecord
from pramana.verification.memory_guard import assert_writable

if TYPE_CHECKING:
    from pramana.contracts import CandidateInsight
    from pramana.memory.config import MemorySettings
    from pramana.memory.fingerprint import DatasetFingerprint
    from pramana.memory.lesson import Lesson

STORE_PATH_ENV = "PRAMANA_MEMORY_STORE"
DEFAULT_STORE_PATH = ARTIFACTS_DIR / "memory" / "verified_insights.jsonl"


def store_path() -> Path:
    """Where records are written: `$PRAMANA_MEMORY_STORE`, else the artifacts default."""
    configured = os.getenv(STORE_PATH_ENV, "").strip()
    return Path(configured) if configured else DEFAULT_STORE_PATH


def _append(path: Path, records: Sequence[VerifiedInsightRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json() + "\n")


def write_proofs(
    proofs: Sequence[ProofObject],
    *,
    run_id: str,
    dataset_ref: str | None,
    path: Path | None = None,
) -> list[VerifiedInsightRecord]:
    """Write every proof, or none of them.

    Guarantees: each proof passes `assert_writable` BEFORE anything is written, so a
    batch containing one non-PASS proof raises `MemoryWriteRefused` and leaves the
    store untouched. There is no argument that skips the guard.
    """
    admitted = [
        assert_writable(ProofObject.model_validate(proof.model_dump(mode="python")))
        for proof in proofs
    ]
    stored_at = datetime.now(UTC)
    records = [
        VerifiedInsightRecord.from_proof(
            proof, run_id=run_id, dataset_ref=dataset_ref, stored_at=stored_at
        )
        for proof in admitted
    ]
    if records:
        _append(path or store_path(), records)
    return records


def read_records(path: Path | None = None) -> list[VerifiedInsightRecord]:
    """Every record in the store, oldest first; an absent store is empty."""
    source = path or store_path()
    if not source.is_file():
        return []
    lines = source.read_text(encoding="utf-8").splitlines()
    return [VerifiedInsightRecord.model_validate_json(line) for line in lines if line.strip()]


def write_verified(request: Mapping[str, Any]) -> dict[str, Any]:
    """Orchestration handler: `MemoryWriteRequest` -> `MemoryWriteResult`.

    Loaded by `PRAMANA_MEMORY_HANDLER=pramana.memory.store:write_verified`. The
    request's proofs are re-validated as `ProofObject`s and go through the guard
    again here: orchestration's own PASS filter is a courtesy, this is the lock.
    """
    proofs = [
        item if isinstance(item, ProofObject) else ProofObject.model_validate(item)
        for item in request["proof_objects"]
    ]
    path = store_path()
    records = write_proofs(
        proofs,
        run_id=str(request["run_id"]),
        dataset_ref=request.get("dataset_ref"),
        path=path,
    )
    return {
        "memory_receipts": [
            {
                "record_id": record.record_id,
                "insight_id": record.insight_id,
                "backend": "jsonl (temporary)",
                "location": str(path),
            }
            for record in records
        ]
    }


class ChromaLessonStore:
    """The only Chroma write boundary; guard the entire batch before embedding/writing.

    The legacy JSONL proof-only handler above remains explicitly separate. This
    store requires the actual candidates and schema and never falls back to JSONL.
    """

    def __init__(
        self, settings: MemorySettings | None = None, *, embedding_function: Any = None
    ) -> None:
        from threading import RLock

        from pramana.memory.config import load_memory_settings

        self.settings = settings or load_memory_settings()
        self._embedding_function = embedding_function
        self._collection: Any = None
        self._lock = RLock()

    def _connect(self) -> Any:
        if self._collection is None:
            import chromadb
            from chromadb.config import Settings
            from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

            from pramana.memory.config import persistent_path

            config = self.settings.chroma
            options = Settings(anonymized_telemetry=False)
            if config.mode == "persistent":
                client = chromadb.PersistentClient(
                    path=str(persistent_path(config)), settings=options
                )
            else:
                client = chromadb.HttpClient(host=config.host, port=config.port, settings=options)
            embedding: Any = self._embedding_function
            if embedding is None:
                embedding = ONNXMiniLM_L6_V2()
                # Keep the model cache inside the ignored project data directory.
                embedding.DOWNLOAD_PATH = (
                    persistent_path(config).parent / "models" / config.embedding_model
                )
            self._collection = client.get_or_create_collection(
                name=config.collection,
                embedding_function=embedding,
                metadata={
                    "hnsw:space": "cosine",
                    "pramana_schema": 1,
                    "embedding_model": config.embedding_model,
                },
            )
            metadata = self._collection.metadata or {}
            if (
                metadata.get("hnsw:space") != "cosine"
                or metadata.get("pramana_schema") != 1
                or metadata.get("embedding_model") != config.embedding_model
            ):
                self._collection = None
                raise ValueError("memory collection has incompatible metric/model/schema")
        return self._collection

    @staticmethod
    def _decode(record_id: str, metadata: dict[str, Any]) -> Lesson:
        from pramana.memory.lesson import Lesson

        lesson = Lesson.model_validate_json(metadata["lesson_json"])
        if (
            record_id != lesson.record_id
            or metadata.get("verdict") != "PASS"
            or metadata.get("run_id") != lesson.run_id
            or metadata.get("insight_id") != lesson.proof.insight_id
            or metadata.get("fingerprint") != lesson.fingerprint.digest
        ):
            raise ValueError("memory index metadata disagrees with guarded lesson")
        return lesson

    def write_lessons(
        self,
        candidates: Sequence[CandidateInsight],
        proofs: Sequence[ProofObject],
        *,
        run_id: str,
        dataset_ref: str,
        fingerprint: DatasetFingerprint,
    ) -> list[Lesson]:
        """Refuse any non-PASS or mismatched batch before touching the vector store."""
        from pramana.contracts import CandidateInsight
        from pramana.memory.abstraction import abstract_lesson
        from pramana.memory.fingerprint import DatasetFingerprint

        admitted = [
            assert_writable(ProofObject.model_validate(item.model_dump(mode="python")))
            for item in proofs
        ]
        if len({proof.insight_id for proof in admitted}) != len(admitted):
            raise ValueError("duplicate proof IDs")
        validated = [
            CandidateInsight.model_validate(item.model_dump(mode="python")) for item in candidates
        ]
        by_id = {item.insight_id: item for item in validated}
        if len(by_id) != len(validated):
            raise ValueError("duplicate candidate IDs")
        fingerprint = DatasetFingerprint.model_validate(fingerprint.model_dump(mode="python"))
        lessons = [
            abstract_lesson(
                by_id[proof.insight_id],
                proof,
                run_id=run_id,
                dataset_ref=dataset_ref,
                fingerprint=fingerprint,
            )
            for proof in admitted
        ]
        if not lessons:
            return []
        with self._lock:
            collection = self._connect()
            existing = collection.get(
                ids=[item.record_id for item in lessons], include=["metadatas"]
            )
            previous = {
                key: self._decode(key, value)
                for key, value in zip(existing["ids"], existing["metadatas"], strict=True)
            }
            for index, lesson in enumerate(lessons):
                if old := previous.get(lesson.record_id):
                    if old.model_dump(exclude={"stored_at"}) != lesson.model_dump(
                        exclude={"stored_at"}
                    ):
                        raise ValueError("conflicting retry for an existing lesson")
                    lessons[index] = old
            fresh = [item for item in lessons if item.record_id not in previous]
            if fresh:
                collection.upsert(
                    ids=[item.record_id for item in fresh],
                    documents=[item.fingerprint.description + "\n" + item.text for item in fresh],
                    metadatas=[
                        {
                            "lesson_json": item.model_dump_json(),
                            "verdict": "PASS",
                            "run_id": item.run_id,
                            "insight_id": item.proof.insight_id,
                            "fingerprint": item.fingerprint.digest,
                        }
                        for item in fresh
                    ],
                )
        return lessons

    def browse(self, *, limit: int = 50, offset: int = 0) -> list[Lesson]:
        """Return validated source lessons only; refuse corrupt persisted proofs."""
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("invalid browse bounds")
        with self._lock:
            result = self._connect().get(limit=limit, offset=offset, include=["metadatas"])
            return [
                self._decode(key, metadata)
                for key, metadata in zip(result["ids"], result["metadatas"], strict=True)
            ]

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        exclude_run_id: str | None = None,
    ) -> list[tuple[Lesson, float]]:
        """Retrieve verified historical hints; cosine similarity never acts as evidence."""
        import math

        count = top_k or self.settings.retrieval.top_k
        if not query.strip() or len(query) > 10000 or not 1 <= count <= 100:
            raise ValueError("invalid search bounds")
        with self._lock:
            collection = self._connect()
            if not collection.count():
                return []
            where: dict[str, Any] = {"verdict": "PASS"}
            if exclude_run_id:
                where = {"$and": [where, {"run_id": {"$ne": exclude_run_id}}]}
            result = collection.query(
                query_texts=[query],
                n_results=count,
                where=where,
                include=["metadatas", "distances"],
            )
            hits = []
            for key, metadata, distance in zip(
                result["ids"][0], result["metadatas"][0], result["distances"][0], strict=True
            ):
                lesson = self._decode(key, metadata)
                similarity = min(1.0, max(-1.0, 1.0 - distance))
                if math.isfinite(distance) and similarity >= self.settings.retrieval.min_similarity:
                    hits.append((lesson, similarity))
            return hits
