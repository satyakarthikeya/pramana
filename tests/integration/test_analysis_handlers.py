"""The analysis handlers satisfy the request/response shapes orchestration validates."""

from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from pramana.analysis import handlers
from pramana.contracts import CandidateInsight, ProofObject
from pramana.orchestration.integration import (
    AnalysisResult,
    IngestResult,
    PreparationResult,
)
from pramana.orchestration.tasks import native_verification_handler
from pramana.verification.gateway import BatchSummary


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


def test_handlers_chain_into_contract_valid_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pramana.analysis.dataset_artifacts.DATA_DIR", tmp_path)
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

    assert Path(prepared.dataset_ref) == tmp_path / "runs" / str(run_id) / "cleaned.pkl"
    pd.testing.assert_frame_equal(pd.read_pickle(prepared.dataset_ref), prepared.dataset)
    assert prepared.schema_profile["cleaned_fingerprint"].startswith(f"{source}#cleaned-sha256:")
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


def test_preparation_artifact_is_accepted_by_the_existing_worker_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pramana.analysis.dataset_artifacts.DATA_DIR", tmp_path)
    run_id = uuid4()
    source = str(_write_csv(tmp_path))
    loaded = handlers.ingest({"run_id": run_id, "dataset_ref": source})
    prepared = handlers.prepare({"run_id": run_id, **loaded})
    candidates = handlers.analyze({"run_id": run_id, **prepared})["candidate_insights"]
    seen: dict[str, object] = {}

    def capture_gateway(
        batch: list[CandidateInsight], frame: pd.DataFrame, _config: object, **_: object
    ) -> tuple[list[ProofObject], BatchSummary]:
        seen["batch"] = batch
        pd.testing.assert_frame_equal(frame, prepared["dataset"])
        return [], BatchSummary(
            bh_family_id="transport-fixture",
            generator="template",
            n_candidates=len(batch),
            n_screened_out=len(batch),
            n_tested=0,
            generator_unavailable_count=0,
            column_check_by_claim_type={},
        )

    # This test covers transport into the worker; real statistical tests remain separate.
    monkeypatch.setattr("pramana.verification.gateway.verify_batch_with_summary", capture_gateway)
    result = native_verification_handler(
        {
            "run_id": str(run_id),
            "dataset_ref": prepared["dataset_ref"],
            "candidate_insights": [item.model_dump(mode="json") for item in candidates],
        },
        data_dir=tmp_path,
    )
    assert seen["batch"] == candidates
    assert result["proof_objects"] == []
    assert result["verification_summary"].n_candidates == len(candidates)
    missing_run = uuid4()
    with pytest.raises(FileNotFoundError):
        native_verification_handler(
            {
                "run_id": str(missing_run),
                "dataset_ref": str(tmp_path / "runs" / str(missing_run) / "cleaned.pkl"),
                "candidate_insights": [],
            },
            data_dir=tmp_path,
        )
