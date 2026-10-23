"""API failure boundaries and durable results, with graph execution injected explicitly."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from pramana.api.main import create_app
from pramana.api.service import RunService
from pramana.contracts import GateOutcome
from pramana.memory.store import ChromaLessonStore
from pramana.orchestration.run_lifecycle import new_run
from pramana.orchestration.state import PramanaState, RunStatus
from tests.unit.memory.test_lessons import TestEmbedding, candidate, settings_for
from tests.unit.memory.test_store import _proof


def finished(run_id: UUID, path: Path, query: str | None) -> PramanaState:
    state = new_run(str(path), user_query=query)
    state.run_id = run_id
    state.status = RunStatus.COMPLETED
    state.candidate_insights = [candidate("ok", str(path)), candidate("bad", str(path))]
    state.proof_objects = [
        _proof("ok", GateOutcome.SUPPORTED),
        _proof("bad", GateOutcome.INCONCLUSIVE),
    ]
    return state


def sign_in(client: TestClient, email: str = "owner@example.com") -> None:
    """Create the account (or sign back in on a restarted server); the cookie is kept."""
    body = {"email": email, "password": "correct horse battery"}
    if client.post("/api/auth/signup", json=body).status_code != 201:
        assert client.post("/api/auth/login", json=body).status_code == 200


def service_for(root: Path, runner=finished, **extra) -> RunService:
    settings = settings_for(root / "chroma")
    return RunService(
        root,
        settings,
        store=ChromaLessonStore(settings, embedding_function=TestEmbedding()),
        runner=runner,
        **extra,
    )


def test_upload_results_status_and_restart_persistence(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        response = client.post("/api/runs", files={"file": ("../../toy.csv", b"a,b\n1,2\n")})
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        status = client.get(f"/api/runs/{run_id}").json()
        assert status["status"] == "completed"
        assert status["file_name"] == "toy.csv"
        result = client.get(f"/api/runs/{run_id}/results").json()
        assert [row["insight_id"] for row in result["verified_insights"]] == ["ok"]
        assert [row["insight_id"] for row in result["rejected_claims"]] == ["bad"]
        assert result["rejected_claims"][0]["proof"]["verdict"] == "REJECT"
        assert client.post("/api/memory", json={"verdict": "PASS"}).status_code == 405
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/runs/not-a-uuid").status_code == 422
        assert client.get(f"/api/runs/{uuid4()}").status_code == 404
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        assert client.get(f"/api/runs/{run_id}/results").json() == result


def test_runner_failure_does_not_expose_secret_exception_or_claims(tmp_path: Path) -> None:
    def broken(*_args):
        raise RuntimeError("sk-secret-key participant-name")

    with TestClient(create_app(service=service_for(tmp_path, broken))) as client:
        sign_in(client)
        run_id = client.post("/api/runs", files={"file": ("toy.csv", b"a\n1\n")}).json()["run_id"]
        response = client.get(f"/api/runs/{run_id}")
        assert response.json()["status"] == "failed"
        assert "sk-secret" not in response.text
        assert client.get(f"/api/runs/{run_id}/results").status_code == 409


def test_unverified_candidates_are_withheld_on_degraded_run(tmp_path: Path) -> None:
    def partial(run_id, path, query):
        state = finished(run_id, path, query)
        state.status = RunStatus.DEGRADED
        state.proof_objects = []
        return state

    with TestClient(create_app(service=service_for(tmp_path, partial))) as client:
        sign_in(client)
        run_id = client.post("/api/runs", files={"file": ("toy.csv", b"a\n1\n")}).json()["run_id"]
        response = client.get(f"/api/runs/{run_id}/results")
        assert response.json()["verified_insights"] == []
        assert response.json()["rejected_claims"] == []
        assert response.json()["unverified_candidate_count"] == 2
        assert "bmi is associated" not in response.text


def test_upload_limits_busy_slot_and_interrupted_recovery(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        assert client.post("/api/runs", files={"file": ("toy.csv", b"")}).status_code == 422
        assert client.post("/api/runs", files={"file": ("x.py", b"code")}).status_code == 415
        assert service.reserve()
        assert client.post("/api/runs", files={"file": ("toy.csv", b"a\n")}).status_code == 429
        service.release()
        owner = UUID(client.get("/api/auth/me").json()["user_id"])
        interrupted = service.repository.create(uuid4(), "interrupted.csv", None, owner)
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        assert client.get(f"/api/runs/{interrupted.run_id}").json()["status"] == "failed"


def test_failed_memory_connection_returns_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = service_for(tmp_path)

    def unavailable(**_kwargs):
        raise ConnectionError("sensitive internal hostname")

    monkeypatch.setattr(service.store, "browse", unavailable)
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        response = client.get("/api/memory")
        assert response.status_code == 503
        assert "sensitive" not in response.text


def test_real_graph_gateway_memory_and_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pramana.api import service as service_module
    from pramana.verification.config import load_config
    from pramana.verification.gateway import verify_batch
    from tests.fixtures.frames import toy_frame

    config = load_config()
    # Explicit test budget; the real library, BH correction, gateway and guard all run.
    config = config.model_copy(
        update={"statistics": config.statistics.model_copy(update={"n_permutations": 1000})}
    )

    def real_gateway(state: PramanaState, *, progress=None) -> dict:
        if progress:
            progress(1, len(state.candidate_insights))
        return {"proof_objects": verify_batch(state.candidate_insights, state.dataset, config)}

    monkeypatch.setattr(service_module, "inprocess_verification_adapter", real_gateway)
    settings = settings_for(tmp_path / "chroma")
    settings = settings.model_copy(
        update={"api": settings.api.model_copy(update={"verification_mode": "inprocess"})}
    )
    store = ChromaLessonStore(settings, embedding_function=TestEmbedding())
    service = RunService(tmp_path, settings, store=store)
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        response = client.post(
            "/api/runs", files={"file": ("toy.csv", toy_frame().to_csv(index=False).encode())}
        )
        run_id = response.json()["run_id"]
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed"
        result = client.get(f"/api/runs/{run_id}/results").json()
        assert result["verified_insights"]
        assert result["rejected_claims"]
        memory = client.get("/api/memory").json()
        assert {item["proof"]["insight_id"] for item in memory} == {
            row["insight_id"] for row in result["verified_insights"]
        }
        assert all(item["proof"]["verdict"] == "PASS" for item in memory)
        hits = client.post("/api/memory/search", json={"query": "age bmi"}).json()
        assert hits
