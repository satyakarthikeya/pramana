"""V1 product acceptance: safe presentation, durable progress and keyless startup."""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from pramana.api.main import create_app
from pramana.api.service import RunService
from pramana.api.v1 import effect_strength, rejection_reason, v1_settings
from pramana.contracts import GateOutcome, ProofObject, Verdict
from pramana.memory.store import ChromaLessonStore
from tests.fixtures.sample_data import SAMPLE_PILOT_ROWS, SAMPLE_ROWS, sample_frame
from tests.unit.api.test_api import service_for, sign_in
from tests.unit.memory.test_lessons import TestEmbedding, settings_for
from tests.unit.memory.test_store import _proof


def run_sample(client: TestClient) -> dict[str, Any]:
    """Upload the test-only synthetic table through the real upload endpoint."""
    content = sample_frame().to_csv(index=False).encode()
    return client.post("/api/runs", files={"file": ("sample.csv", content)}).json()


def real_service(root: Path) -> RunService:
    settings = settings_for(root / "chroma")
    settings = settings.model_copy(
        update={"api": settings.api.model_copy(update={"verification_mode": "inprocess"})}
    )
    return RunService(
        root, settings, store=ChromaLessonStore(settings, embedding_function=TestEmbedding())
    )


def test_one_command_start_defaults_are_explicit_and_keys_are_not_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pramana.__main__ import main

    monkeypatch.delenv("PRAMANA_VERIFICATION_GENERATOR", raising=False)
    monkeypatch.delenv("PRAMANA_API_VERIFICATION_MODE", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sys, "argv", ["pramana", "--port", "8089"])
    captured: dict[str, Any] = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: captured.update(app=app, **kw))
    main()
    import os

    assert os.environ["PRAMANA_VERIFICATION_GENERATOR"] == "template"
    assert os.environ["PRAMANA_API_VERIFICATION_MODE"] == "inprocess"
    assert captured == {"app": "pramana.api.main:app", "host": "127.0.0.1", "port": 8089}


def test_deepseek_analysis_failure_is_safe_and_actionable_in_website_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRAMANA_ANALYSIS_ENGINE", "api")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(
        "pramana.analysis.hypotheses.llm_proposer.get_langfuse_client", lambda _: None
    )
    with TestClient(create_app(service=real_service(tmp_path))) as client:
        sign_in(client)
        run_id = run_sample(client)["run_id"]
        view = client.get(f"/api/runs/{run_id}").json()
        assert view["status"] == "degraded"
        assert "Analysis model unavailable" in view["error"]
        assert "DEEPSEEK_API_KEY" in view["error"]
        results = client.get(f"/api/runs/{run_id}/results").json()
        assert results["verified_insights"] == []
        assert results["candidate_count"] == 0
        assert client.get("/api/memory").json() == []


@pytest.mark.parametrize(
    "content, message",
    [
        (b"a,b\n", "no data rows"),
        (b"constant\n1\n1\n1\n", "No usable"),
        (b"a,b\n\xff,1\n", "could not be read"),
    ],
)
def test_bad_tables_have_friendly_messages_without_tracebacks(
    tmp_path: Path,
    content: bytes,
    message: str,
) -> None:
    with TestClient(create_app(service=real_service(tmp_path))) as client:
        sign_in(client)
        run_id = client.post("/api/runs", files={"file": ("input.csv", content)}).json()["run_id"]
        view = client.get(f"/api/runs/{run_id}").json()
        assert view["status"] == "degraded"
        assert message in view["error"]
        assert "Traceback" not in str(view)
        assert client.get(f"/api/runs/{run_id}/results").json()["verified_insights"] == []


def test_synthetic_test_table_is_reproducible_and_runs_through_upload(tmp_path: Path) -> None:
    first, second = sample_frame(), sample_frame()
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == SAMPLE_ROWS
    assert first["moon_phase_pilot"].notna().sum() == SAMPLE_PILOT_ROWS
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        assert client.get("/api/sample").status_code == 404
        assert client.post("/api/runs/sample").status_code in {404, 405}
        run = run_sample(client)
        assert client.get(f"/api/runs/{run['run_id']}").json()["status"] == "completed"


def test_preview_progress_cap_and_two_run_hints_keep_pass_only_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pramana.verification.config import load_config

    config = load_config()
    fast = config.model_copy(
        update={"statistics": config.statistics.model_copy(update={"n_permutations": 199})}
    )
    monkeypatch.setattr("pramana.verification.config.load_config", lambda: fast)
    service = real_service(tmp_path)
    seen: list[str] = []
    progress = service.repository.progress

    def record(run_id: UUID, stage: str, **details: Any) -> None:
        seen.append(stage)
        progress(run_id, stage, **details)

    monkeypatch.setattr(service.repository, "progress", record)
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        for index in range(2):
            run_id = run_sample(client)["run_id"]
            view = client.get(f"/api/runs/{run_id}").json()
            assert view["status"] == "completed", view
            assert view["preview"]["rows"] == SAMPLE_ROWS
            assert any(not column["usable"] for column in view["preview"]["detected_columns"])
            if index:
                assert view["past_lessons"]
                assert all(hit["lesson"]["run_id"] != run_id for hit in view["past_lessons"])
            result = client.get(f"/api/runs/{run_id}/results").json()
            assert 0 < result["candidate_count"] <= v1_settings().max_candidates
            # The proposer explores half the rows (PLAN D5), so the sample's decoy pairs no
            # longer always clear its scan; a real pair must still be proposed and verified.
            assert result["verified_insights"]
            rows = result["verified_insights"] + result["rejected_claims"]
            assert all(row["claim_type"] for row in rows)
            assert all(row["explanation"] for row in result["rejected_claims"])
            look = result["exploration"]
            assert look["engine"] == "scan" and look["examined"] >= look["proposed"] > 0
            assert look["tested"] == len(result["verified_insights"]) + len(
                result["rejected_claims"]
            )
            for row in result["verified_insights"]:
                assert row["effect_strength"] and row["complete_rows"]
                assert row["n_permutations"] == 199
            memory = client.get("/api/memory").json()
            assert all(lesson["proof"]["verdict"] == "PASS" for lesson in memory)
            assert {
                lesson["proof"]["insight_id"] for lesson in memory if lesson["run_id"] == run_id
            } == {row["insight_id"] for row in result["verified_insights"]}
    assert "Reading data" in seen and "Writing verified memory" in seen
    assert any(stage.startswith("Checking claim") for stage in seen)


def test_exports_are_downloadable_proof_bearing_and_guard_csv_formulas(tmp_path: Path) -> None:
    from tests.unit.api.test_api import finished

    def formula(run_id: UUID, path: Path, query: str | None) -> Any:
        state = finished(run_id, path, query)
        state.candidate_insights[0] = state.candidate_insights[0].model_copy(
            update={"claim": '=HYPERLINK("https://invalid.example")'}
        )
        return state

    with TestClient(create_app(service=service_for(tmp_path, formula))) as client:
        sign_in(client)
        run_id = client.post("/api/runs", files={"file": ("table.csv", b"a,b\n1,2")}).json()[
            "run_id"
        ]
        response = client.get(f"/api/runs/{run_id}/export/json")
        assert response.status_code == 200
        assert response.json()["verified_insights"][0]["proof"]["verdict"] == "PASS"
        response = client.get(f"/api/runs/{run_id}/export/csv")
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert rows[0]["claim"].startswith("'=")
        assert rows[1]["is_finding"] == "False"
        assert client.get(f"/api/runs/{run_id}/export/html").status_code == 404


def test_strength_words_use_existing_configured_bands_and_reasons_are_safe() -> None:
    proof = _proof("a", GateOutcome.SUPPORTED)
    assert effect_strength(proof) in {"medium", "large"}
    unavailable = ProofObject(
        insight_id="b",
        verdict=Verdict.REJECT,
        gate_outcome=GateOutcome.NOT_TESTABLE,
        bh_family_id="bh-test",
        seed=1,
        failure_reason="generator unavailable: secret-token",
    )
    assert "unavailable" in rejection_reason(unavailable)
    assert "secret-token" not in rejection_reason(unavailable)


def test_generator_unavailable_is_an_explicit_api_error_with_retained_proofs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "llm")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    # 80 rows: the proposer explores half of them (PLAN D5) and needs 20 or more
    content = pd.DataFrame({"x": range(80), "y": range(80)}).to_csv(index=False).encode()
    with TestClient(create_app(service=real_service(tmp_path))) as client:
        sign_in(client)
        run_id = client.post("/api/runs", files={"file": ("table.csv", content)}).json()["run_id"]
        view = client.get(f"/api/runs/{run_id}").json()
        assert view["status"] == "degraded"
        assert "generator unavailable" in view["error"]
        result = client.get(f"/api/runs/{run_id}/results").json()
        assert result["rejected_claims"] and result["verified_insights"] == []
        assert all(row["proof"]["p_value"] is None for row in result["rejected_claims"])
        assert client.get("/api/memory").json() == []


def test_trend_table_above_documented_ceiling_refuses_without_sampling(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {"measurement_date": pd.date_range("2020-01-01", periods=3001), "measurement": range(3001)}
    )
    with TestClient(create_app(service=real_service(tmp_path))) as client:
        sign_in(client)
        run_id = client.post(
            "/api/runs", files={"file": ("trend.csv", frame.to_csv(index=False).encode())}
        ).json()["run_id"]
        view = client.get(f"/api/runs/{run_id}").json()
        assert view["status"] == "degraded"
        assert "3000" in view["error"] and "silently sampled" in view["error"]
        assert view["preview"]["rows"] == 3001


def test_upload_size_error_is_friendly_and_releases_capacity(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    service.settings = service.settings.model_copy(
        update={"api": service.settings.api.model_copy(update={"max_upload_mb": 1})}
    )
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        response = client.post("/api/runs", files={"file": ("large.csv", b"x" * (1024**2 + 1))})
        assert response.status_code == 413 and "size limit" in response.json()["detail"]
        assert service.reserve()
        service.release()
