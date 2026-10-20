"""Exercise real MiniLM embeddings and persistent memory with a gateway-verified toy claim."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pramana.analysis.config import load_config as analysis_config  # noqa: E402
from pramana.analysis.schema_inference import infer_schema  # noqa: E402
from pramana.contracts import CandidateInsight, ClaimType, Direction, Verdict  # noqa: E402
from pramana.memory.config import load_memory_settings  # noqa: E402
from pramana.memory.fingerprint import fingerprint_schema  # noqa: E402
from pramana.memory.store import ChromaLessonStore  # noqa: E402
from pramana.verification.config import load_config  # noqa: E402
from pramana.verification.gateway import verify_batch  # noqa: E402


def main() -> None:
    """Fail unless a real template-verification proof survives persistent store and retrieval."""
    config = load_config()
    if config.llm.generator != "template":
        raise RuntimeError(
            "This offline smoke check requires explicit template config; no fallback"
        )
    rng = np.random.default_rng(config.statistics.seed)
    age = rng.normal(45, 10, 120)
    frame = pd.DataFrame({"age": age, "bmi": age * 0.3 + rng.normal(0, 0.1, 120)})
    run_id = str(uuid4())
    ref = "synthetic-memory-smoke:" + run_id
    candidate = CandidateInsight(
        insight_id="age-bmi",
        claim="bmi is associated with age",
        claim_type=ClaimType.CORRELATION,
        variables=["age", "bmi"],
        dataset_ref=ref,
        asserted_direction=Direction.POSITIVE,
    )
    proofs = verify_batch([candidate], frame, config)
    if proofs[0].verdict is not Verdict.PASS:
        raise RuntimeError("Synthetic known-effect smoke claim did not pass the real gateway")
    settings = load_memory_settings()
    values = settings.model_dump()
    values["chroma"].update(
        mode="persistent",
        collection="memory_smoke",
        persist_path=str(ROOT / "data/memory-smoke/chroma"),
    )
    settings = type(settings).model_validate(values)
    fingerprint = fingerprint_schema(infer_schema(frame, analysis_config().schema_inference))
    store = ChromaLessonStore(settings)
    written = store.write_lessons(
        [candidate], proofs, run_id=run_id, dataset_ref=ref, fingerprint=fingerprint
    )
    reopened = ChromaLessonStore(settings)
    hits = reopened.search(fingerprint.description, top_k=100)
    if not any(lesson.record_id == written[0].record_id for lesson, _ in hits):
        raise RuntimeError(
            "Persistent semantic retrieval did not return the verified source lesson"
        )
    report = {
        "embedding_model": settings.chroma.embedding_model,
        "backend": "persistent_chromadb",
        "generator": config.llm.generator,
        "seed": config.statistics.seed,
        "n_permutations": config.statistics.n_permutations,
        "run_id": run_id,
        "gateway_verdict": proofs[0].verdict.value,
        "reopened_retrieval": "passed",
        "synthetic_data_only": True,
    }
    target = ROOT / "artifacts/verified_memory_smoke.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
