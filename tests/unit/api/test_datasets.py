"""Datasets are stored once, profiled by code, and analysed through the same gate."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pramana.api.main import create_app
from tests.fixtures.sample_data import SAMPLE_ROWS, sample_frame
from tests.unit.api.test_api import service_for, sign_in


def _csv() -> bytes:
    return sample_frame().to_csv(index=False).encode()


def test_upload_profiles_the_table_without_running_anything(tmp_path: Path) -> None:
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        response = client.post("/api/datasets", files={"file": ("bp.csv", _csv())})
        assert response.status_code == 201
        view = response.json()
        assert view["name"] == "bp.csv"
        assert view["preview"]["rows"] == SAMPLE_ROWS
        assert view["usable_columns"] >= 2
        assert any(not c["usable"] for c in view["preview"]["detected_columns"])
        assert [c["name"] for c in view["overview"]["columns"]][:2] == ["age_years", "systolic_bp"]
        assert view["overview"]["correlations"] is not None
        assert client.get("/api/runs").json() == []
        assert client.get(f"/api/datasets/{view['dataset_id']}").json() == view


def test_listing_counts_runs_and_runs_link_back_to_their_dataset(tmp_path: Path) -> None:
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        dataset = client.post("/api/datasets", files={"file": ("bp.csv", _csv())}).json()
        listed = client.get("/api/datasets").json()
        assert [d["run_count"] for d in listed] == [0]
        assert listed[0]["last_status"] is None
        run = client.post(f"/api/datasets/{dataset['dataset_id']}/runs").json()
        assert run["dataset_id"] == dataset["dataset_id"]
        assert client.get(f"/api/runs/{run['run_id']}").json()["status"] == "completed"
        assert [
            r["run_id"] for r in client.get(f"/api/datasets/{dataset['dataset_id']}/runs").json()
        ] == [run["run_id"]]
        after = client.get("/api/datasets").json()[0]
        assert after["run_count"] == 1
        assert after["last_status"] == "completed"


def test_bad_uploads_are_refused_with_plain_messages(tmp_path: Path) -> None:
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        assert client.post("/api/datasets", files={"file": ("a.txt", b"x")}).status_code == 415
        empty = client.post("/api/datasets", files={"file": ("a.csv", b"")})
        assert empty.status_code == 422
        header_only = client.post("/api/datasets", files={"file": ("a.csv", b"a,b\n")})
        assert header_only.status_code == 422
        assert "no data rows" in header_only.json()["detail"]
        unreadable = client.post("/api/datasets", files={"file": ("a.csv", b"a,b\n\xff,1\n")})
        assert unreadable.status_code == 422
        assert "could not be read" in unreadable.json()["detail"]
        assert "Traceback" not in unreadable.text
        assert client.get("/api/datasets").json() == []
        assert not list((tmp_path / "api/datasets").glob("*/*"))


def test_a_table_with_no_usable_columns_is_stored_but_cannot_be_analysed(tmp_path: Path) -> None:
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        stored = client.post("/api/datasets", files={"file": ("c.csv", b"constant\n1\n1\n1\n")})
        assert stored.status_code == 201
        assert stored.json()["usable_columns"] == 0
        refused = client.post(f"/api/datasets/{stored.json()['dataset_id']}/runs")
        assert refused.status_code == 422
        assert "No usable" in refused.json()["detail"]


def test_unknown_dataset_is_a_404(tmp_path: Path) -> None:
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        missing = "00000000-0000-0000-0000-000000000000"
        assert client.get(f"/api/datasets/{missing}").status_code == 404
        assert client.post(f"/api/datasets/{missing}/runs").status_code == 404


def test_upload_includes_the_data_readers_brief_and_old_datasets_get_one(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        view = client.post("/api/datasets", files={"file": ("bp.csv", _csv())}).json()
        brief = view["brief"]
        assert brief["headline"].startswith(f"{SAMPLE_ROWS} rows")
        names = {c["name"]: c for c in brief["columns"]}
        # Cleaning removes the constant column, so the preview (not the brief) reports it.
        assert "constant_column" not in names
        excluded = {
            c["name"]: c for c in view["preview"]["detected_columns"] if c["role"] == "excluded"
        }
        assert "constant_column" in excluded
        assert any(n["kind"] == "high_missing" for n in names["moon_phase_pilot"]["notes"])
        assert [n["kind"] for n in names["age_years"]["notes"]] == ["unit_hint"]
        # A dataset stored before the reader existed gets its brief the first time it is opened.
        import sqlite3

        with sqlite3.connect(tmp_path / "api/runs.sqlite3") as connection:
            stored = connection.execute("SELECT view_json FROM datasets").fetchone()[0]
            import json

            legacy = json.loads(stored)
            legacy.pop("brief")
            connection.execute("UPDATE datasets SET view_json = ?", (json.dumps(legacy),))
        again = client.get(f"/api/datasets/{view['dataset_id']}").json()
        assert again["brief"] == brief


def _finance_csv() -> bytes:
    from tests.unit.analysis.computed_fixtures import finance_year

    return finance_year().to_csv(index=False).encode()


def test_upload_includes_the_exact_tier_with_sector_and_shape(tmp_path: Path) -> None:
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        view = client.post("/api/datasets", files={"file": ("pl.csv", _finance_csv())}).json()
        computed = view["computed"]
        assert computed["sector"]["sector"] == "finance"
        assert computed["shape"]["shape"] == "panel"
        kinds = {item["kind"] for item in computed["items"]}
        assert {"period_change", "variance_decomposition", "identity"} <= kinds
        assert all(item["level"] == "exact" for item in computed["items"])


def test_the_model_summary_is_written_after_upload_without_blocking_it(
    tmp_path: Path, monkeypatch
) -> None:
    from pramana.analysis.computed.models import ReportSummary, SummaryLine
    from pramana.api import datasets

    monkeypatch.setenv("PRAMANA_SUMMARY_ENGINE", "api")
    calls = []

    def fake(result, *, engine, trace_id, chat=None):
        calls.append((engine, trace_id))
        first = result.items[0]
        return ReportSummary(source="model", lines=[SummaryLine(item_id=first.id, text="x")])

    monkeypatch.setattr(datasets, "summarise", fake)
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        view = client.post("/api/datasets", files={"file": ("pl.csv", _finance_csv())}).json()
        assert view["computed"]["summary"]["source"] == "template"  # the upload reply
        again = client.get(f"/api/datasets/{view['dataset_id']}").json()
        assert again["computed"]["summary"]["source"] == "model"
        assert calls == [("api", __import__("uuid").UUID(view["dataset_id"]))]
        client.get(f"/api/datasets/{view['dataset_id']}")
        assert len(calls) == 1  # never re-asked once a model summary is stored


def test_an_older_analysis_version_is_rebuilt_on_open(tmp_path: Path) -> None:
    import json
    import sqlite3

    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        view = client.post("/api/datasets", files={"file": ("pl.csv", _finance_csv())}).json()
        with sqlite3.connect(tmp_path / "api/runs.sqlite3") as connection:
            stored = json.loads(connection.execute("SELECT view_json FROM datasets").fetchone()[0])
            stored["computed"]["version"] = 1
            for item in stored["computed"]["items"]:
                item.pop("chart", None)
            connection.execute("UPDATE datasets SET view_json = ?", (json.dumps(stored),))
        reopened = client.get(f"/api/datasets/{view['dataset_id']}").json()
        assert reopened["computed"]["version"] == view["computed"]["version"]
        assert any(item["chart"] for item in reopened["computed"]["items"])


def test_the_sector_is_decided_by_the_system_with_no_user_switch(tmp_path: Path) -> None:
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        view = client.post("/api/datasets", files={"file": ("pl.csv", _finance_csv())}).json()
        put = client.put(f"/api/datasets/{view['dataset_id']}/sector", json={"sector": "health"})
        assert put.status_code in {404, 405}


def test_the_user_names_the_dataset_at_upload(tmp_path: Path) -> None:
    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        named = client.post(
            "/api/datasets",
            files={"file": ("pl.csv", _finance_csv())},
            data={"name": "  Sales   FY2025 "},
        ).json()
        assert named["name"] == "Sales FY2025"
        assert client.get("/api/datasets").json()[0]["name"] == "Sales FY2025"
        unnamed = client.post("/api/datasets", files={"file": ("pl.csv", _finance_csv())}).json()
        assert unnamed["name"] == "pl.csv"
        too_long = client.post(
            "/api/datasets", files={"file": ("pl.csv", _finance_csv())}, data={"name": "x" * 121}
        )
        assert too_long.status_code == 422


def test_old_datasets_get_the_exact_tier_and_a_stale_one_never_breaks_them(tmp_path: Path) -> None:
    import json
    import sqlite3

    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        view = client.post("/api/datasets", files={"file": ("pl.csv", _finance_csv())}).json()
        with sqlite3.connect(tmp_path / "api/runs.sqlite3") as connection:
            stored = json.loads(connection.execute("SELECT view_json FROM datasets").fetchone()[0])
            stored["computed"] = {"an_old_format": True}
            connection.execute("UPDATE datasets SET view_json = ?", (json.dumps(stored),))
        reopened = client.get(f"/api/datasets/{view['dataset_id']}")
        assert reopened.status_code == 200
        assert reopened.json()["computed"] == view["computed"]


def test_a_brief_written_by_an_older_version_never_breaks_a_saved_dataset(tmp_path: Path) -> None:
    import json
    import sqlite3

    with TestClient(create_app(service=service_for(tmp_path))) as client:
        sign_in(client)
        dataset = client.post("/api/datasets", files={"file": ("bp.csv", _csv())}).json()
        with sqlite3.connect(tmp_path / "api/runs.sqlite3") as connection:
            stored = json.loads(connection.execute("SELECT view_json FROM datasets").fetchone()[0])
            stored["brief"]["columns"][0]["notes"] = [
                {"kind": "a_kind_that_no_longer_exists", "level": "note", "message": "old"}
            ]
            connection.execute("UPDATE datasets SET view_json = ?", (json.dumps(stored),))
        listed = client.get("/api/datasets")
        assert listed.status_code == 200 and len(listed.json()) == 1
        reopened = client.get(f"/api/datasets/{dataset['dataset_id']}")
        assert reopened.status_code == 200
        assert reopened.json()["brief"]["headline"] == dataset["brief"]["headline"]
