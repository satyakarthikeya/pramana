"""The advisory step through the API: it can add notes to results and can never change a verdict."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from pramana.analysis import infer_schema, load_config
from pramana.api.main import create_app
from pramana.api.models import RunResults
from pramana.common.llm_client import ChatMessage, Completion
from pramana.contracts import CandidateInsight, ClaimType, Direction, GateOutcome
from pramana.orchestration.run_lifecycle import new_run
from pramana.orchestration.state import PramanaState, RunStatus
from tests.unit.api.test_api import service_for, sign_in
from tests.unit.memory.test_store import _proof


def confounded_frame() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    z = rng.normal(size=400)
    return pd.DataFrame(
        {
            "x": z + rng.normal(scale=0.7, size=400),
            "y": z + rng.normal(scale=0.7, size=400),
            "z": z,
            "noise": rng.normal(size=400),
        }
    )


def runner(run_id: UUID, path: Path, query: str | None) -> PramanaState:
    frame = confounded_frame()
    state = new_run(str(path), user_query=query)
    state.run_id = run_id
    state.status = RunStatus.COMPLETED
    state.dataset = frame
    state.schema_profile = infer_schema(frame, load_config().schema_inference).model_dump(
        mode="json"
    )
    ok = CandidateInsight(
        insight_id="ok",
        claim="y is positively associated with x",
        claim_type=ClaimType.CORRELATION,
        variables=["x", "y"],
        dataset_ref=str(path),
        asserted_direction=Direction.POSITIVE,
    )
    bad = CandidateInsight(
        insight_id="bad",
        claim="noise is positively associated with x",
        claim_type=ClaimType.CORRELATION,
        variables=["x", "noise"],
        dataset_ref=str(path),
        asserted_direction=Direction.POSITIVE,
    )
    state.candidate_insights = [ok, bad]
    state.proof_objects = [
        _proof("ok", GateOutcome.SUPPORTED),
        _proof("bad", GateOutcome.INCONCLUSIVE),
    ]
    return state


def run(client: TestClient) -> dict:
    sign_in(client)
    response = client.post("/api/runs", files={"file": ("toy.csv", b"a,b\n1,2\n")})
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed"
    return client.get(f"/api/runs/{run_id}/results").json()


def test_findings_get_a_summary_and_a_confound_caveat_and_rejections_get_neither(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRAMANA_EXPLAINER_ENGINE", "template")
    with TestClient(create_app(service=service_for(tmp_path, runner))) as client:
        results = run(client)
    advisory = results["advisory"]
    assert [e["insight_id"] for e in advisory["explanations"]] == ["ok"]
    explanation = advisory["explanations"][0]
    assert explanation["source"] == "template" and explanation["fallback_reason"] is None
    assert "it does not show that one thing causes the other" in explanation["text"]
    assert "q = 0.004" in explanation["text"]  # the proof's own q-value, written by code
    assert [r["insight_id"] for r in advisory["reviews"]] == ["ok"]
    review = advisory["reviews"][0]
    assert review["status"] == "flagged" and review["caveats"][0]["control"] == "z"
    assert any("cannot change a verdict" in n for n in advisory["notes"])
    assert [r["insight_id"] for r in results["rejected_claims"]] == ["bad"]


def test_the_verdicts_and_proofs_are_identical_with_and_without_the_advisory_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with TestClient(create_app(service=service_for(tmp_path / "with", runner))) as client:
        with_advisory = run(client)
    monkeypatch.setattr(
        "pramana.api.service.advise", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    with TestClient(create_app(service=service_for(tmp_path / "without", runner))) as client:
        without = run(client)
    assert with_advisory["advisory"] is not None and without["advisory"] is None
    for key in ("verified_insights", "rejected_claims", "candidate_count"):
        assert json.dumps(with_advisory[key], sort_keys=True) == json.dumps(
            without[key], sort_keys=True
        ), key
    assert with_advisory["run"]["status"] == without["run"]["status"] == "completed"


def test_a_crashing_advisory_step_does_not_fail_the_run_or_leak_the_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("sk-secret-key participant-name")

    monkeypatch.setattr("pramana.api.service.advise", boom)
    with TestClient(create_app(service=service_for(tmp_path, runner))) as client:
        results = run(client)
        text = json.dumps(results)
    assert results["advisory"] is None and results["run"]["error"] is None
    assert [r["insight_id"] for r in results["verified_insights"]] == ["ok"]
    assert "sk-secret" not in text


def test_the_advisory_step_never_touches_verified_memory(tmp_path: Path) -> None:
    service = service_for(tmp_path, runner)
    with TestClient(create_app(service=service)) as client:
        results = run(client)
        assert results["advisory"]["reviews"][0]["status"] == "flagged"
        assert client.get("/api/memory").json() == []
    assert service.store.browse(limit=100) == []
    package = Path(__file__).resolve().parents[3] / "src" / "pramana" / "advisory"
    for source in package.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert "pramana.memory" not in text and "write_lessons" not in text, source.name


def test_results_saved_before_the_advisory_step_existed_still_load(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(service=service_for(tmp_path, runner))) as client:
        results = run(client)
    results.pop("advisory")
    assert RunResults.model_validate(results).advisory is None


def test_exports_still_work_with_advisory_notes_present(tmp_path: Path) -> None:
    with TestClient(create_app(service=service_for(tmp_path, runner))) as client:
        sign_in(client)
        response = client.post("/api/runs", files={"file": ("toy.csv", b"a,b\n1,2\n")})
        run_id = response.json()["run_id"]
        assert client.get(f"/api/runs/{run_id}/export/csv").status_code == 200
        exported = client.get(f"/api/runs/{run_id}/export/json")
        assert exported.status_code == 200 and "explanations" in exported.text


def test_a_configured_model_wording_is_checked_through_the_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRAMANA_EXPLAINER_ENGINE", "api")
    sentences = iter(
        [
            json.dumps(
                {
                    "summaries": [
                        {"insight_id": "ok", "text": "Where x is higher, y tends to be higher."}
                    ]
                }
            )
        ]
    )

    def chat(_messages: Sequence[ChatMessage]) -> Completion:
        return Completion(content=next(sentences), input_tokens=100, output_tokens=20)

    service = service_for(tmp_path, runner, advisory_chat=chat)
    with TestClient(create_app(service=service)) as client:
        results = run(client)
    explanation = results["advisory"]["explanations"][0]
    assert explanation["source"] == "model"
    assert explanation["text"].startswith("Where x is higher, y tends to be higher.")
    assert "q = 0.004" in explanation["text"]
    assert results["verified_insights"][0]["proof"]["verdict"] == "PASS"
