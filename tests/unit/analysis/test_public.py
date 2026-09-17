from pathlib import Path

import pandas as pd

from pramana.analysis.benchmark.demo_dataset import create_demo_dataset
from pramana.analysis.public import analyze, ingest, prepare
from pramana.contracts import CandidateInsight


def test_public_handlers_produce_contract_candidates_and_shared_ref(tmp_path: Path) -> None:
    source = create_demo_dataset(tmp_path / "demo.csv", rows=40)

    ingested = ingest(source)
    prepared = prepare(ingested)
    result = analyze(prepared)

    assert prepared["dataset_ref"].endswith(".cleaned.pkl")
    candidates = result["candidate_insights"]
    assert candidates
    assert len({candidate.insight_id for candidate in candidates}) == len(candidates)
    assert all(isinstance(candidate, CandidateInsight) for candidate in candidates)
    assert all(candidate.dataset_ref == prepared["dataset_ref"] for candidate in candidates)
    assert all(candidate.claim_type.value != "distribution" for candidate in candidates)


def test_public_analysis_emits_trend_and_respects_candidate_cap(tmp_path: Path) -> None:
    source = tmp_path / "dated.csv"
    pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=30),
            "score": range(30),
            "group": ["a", "b"] * 15,
        }
    ).to_csv(source, index=False)

    prepared = prepare(ingest(source))
    candidates = analyze(prepared, config={"max_candidates": 1})["candidate_insights"]

    assert len(candidates) == 1
    assert candidates[0].dataset_ref == prepared["dataset_ref"]
