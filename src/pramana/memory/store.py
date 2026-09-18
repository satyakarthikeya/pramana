"""The single write path. Wraps verification.memory_guard before any write.

No other file in this repo may import chromadb -- there is a test that greps
for it and fails the build (SCOPE_M 4 step 2).

TEMPORARY BACKEND. Records are appended to a local JSONL file, not ChromaDB.
chromadb is not installed in the project environment yet, and standing it up
(plus an embedding model) would have blocked the first end-to-end run. The guard
wiring is the part that has to be right, and it is backend-independent: swapping
`_append` for a ChromaDB upsert changes nothing above it. The file lives under
the gitignored `artifacts/` unless `PRAMANA_MEMORY_STORE` points elsewhere.

Owner: M. Karthik Reddy
Scope: scope/SCOPE_M_Karthik_Reddy.md
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pramana.common.paths import ARTIFACTS_DIR
from pramana.contracts import ProofObject
from pramana.memory.schema import VerifiedInsightRecord
from pramana.verification.memory_guard import assert_writable

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
    admitted = [assert_writable(proof) for proof in proofs]
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
