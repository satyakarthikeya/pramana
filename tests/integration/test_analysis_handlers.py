"""The analysis handlers satisfy the request/response shapes orchestration validates."""

from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from pramana.analysis import handlers
from pramana.contracts import CandidateInsight
from pramana.orchestration.integration import (
    AnalysisResult,
    IngestResult,
    PreparationResult,
)


def _write_csv(tmp_path: Path) -> Path:
    rng = np.random.default_rng(3)
    x = rng.normal(size=200)
    frame = pd.DataFrame(
        {
            "exposure": x,
            "outcome": 2 * x + rng.normal(scale=0.5, size=200),
            "group": rng.choice(["a", "b"], 200),
            "constant": 1,
        }
    )
    path = tmp_path / "toy.csv"
    frame.to_csv(path, index=False)
    return path


def test_handlers_chain_into_contract_valid_candidates(tmp_path: Path) -> None:
    run_id = uuid4()
    source = str(_write_csv(tmp_path))

    ingested = IngestResult.model_validate(
        handlers.ingest({"run_id": run_id, "dataset_ref": source})
    )
    prepared = PreparationResult.model_validate(
        handlers.prepare(
            {"run_id": run_id, "dataset": ingested.dataset, "dataset_ref": ingested.dataset_ref}
        )
    )
    analysed = AnalysisResult.model_validate(
        handlers.analyze(
            {
                "run_id": run_id,
                "dataset": prepared.dataset,
                "dataset_ref": prepared.dataset_ref,
                "schema_profile": prepared.schema_profile,
                "user_query": None,
            }
        )
    )

    assert prepared.dataset_ref.startswith(f"{source}#cleaned-sha256:")
    assert "constant" not in prepared.dataset.columns
    assert "cleaning_report" in prepared.schema_profile
    assert analysed.candidate_insights
    assert all(isinstance(item, CandidateInsight) for item in analysed.candidate_insights)
    assert {item.dataset_ref for item in analysed.candidate_insights} == {prepared.dataset_ref}


def test_the_cleaned_reference_tracks_the_values() -> None:
    frame = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
    same = handlers.cleaned_dataset_ref("f.csv", frame.copy())
    assert handlers.cleaned_dataset_ref("f.csv", frame) == same

    changed = frame.copy()
    changed.loc[0, "a"] = 9.0
    assert handlers.cleaned_dataset_ref("f.csv", changed) != same
