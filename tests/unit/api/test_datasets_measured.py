"""The Measured tier is built after an upload, stored on the dataset, and rebuilt when stale."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from pramana.analysis.measured import MEASURED_VERSION
from pramana.api import datasets as datasets_module
from pramana.api.main import create_app
from tests.unit.analysis import measured_fixtures as fx
from tests.unit.api.test_api import service_for, sign_in


@pytest.fixture
def measured_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRAMANA_MEASURED_ENABLED", "1")
    monkeypatch.setattr(datasets_module, "load_measured_config", lambda: fx.fast_config())


def _csv() -> bytes:
    return fx.driver_table(n=150).to_csv(index=False).encode()


def test_upload_is_pending_then_the_measured_tier_is_stored(
    tmp_path: Path, measured_on: None
) -> None:
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        uploaded = client.post("/api/datasets", files={"file": ("sales.csv", _csv())}).json()
        # the response did not wait for the models
        assert uploaded["measured"] is None and uploaded["measured_pending"] is True
        stored = client.get(f"/api/datasets/{uploaded['dataset_id']}").json()
        assert stored["measured_pending"] is False
        measured = stored["measured"]
        assert measured["version"] == MEASURED_VERSION
        assert measured["seed"] == fx.fast_config().seed
        kinds = {item["kind"] for item in measured["items"]}
        assert "driver_regression" in kinds
        assert all(item["level"] == "measured" for item in measured["items"])
        assert stored["measured_failed_version"] == 0
        # the Exact tier and the summary written meanwhile are untouched
        assert stored["computed"] is not None


def test_a_stale_measured_tier_is_rebuilt_on_open(tmp_path: Path, measured_on: None) -> None:
    service = service_for(tmp_path)
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        uploaded = client.post("/api/datasets", files={"file": ("sales.csv", _csv())}).json()
        dataset_id = UUID(uploaded["dataset_id"])
        built = service.datasets.get(dataset_id)
        assert built.measured is not None
        stale = built.model_copy(
            update={"measured": built.measured.model_copy(update={"version": 0})}
        )
        service.datasets._save(stale)
        assert service.datasets.needs_measured(stale)
        client.get(f"/api/datasets/{dataset_id}")
        assert service.datasets.get(dataset_id).measured.version == MEASURED_VERSION  # type: ignore[union-attr]


def test_a_failed_build_is_recorded_and_not_retried(
    tmp_path: Path, measured_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(datasets_module, "measured_tier", lambda *a, **k: None)
    service = service_for(tmp_path)
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        uploaded = client.post("/api/datasets", files={"file": ("sales.csv", _csv())}).json()
        view = service.datasets.get(UUID(uploaded["dataset_id"]))
        assert view.measured is None
        assert view.measured_failed_version == MEASURED_VERSION
        assert view.measured_pending is False
        assert not service.datasets.needs_measured(view)


def test_the_tier_stays_off_when_disabled(tmp_path: Path) -> None:
    # conftest pins PRAMANA_MEASURED_ENABLED=0
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        uploaded = client.post("/api/datasets", files={"file": ("sales.csv", _csv())}).json()
        assert uploaded["measured"] is None and uploaded["measured_pending"] is False
