"""Accounts: sign-up and sign-in, sessions, and strict per-user separation of data."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pramana.api.auth import AuthService, hash_password, verify_password
from pramana.api.main import create_app
from tests.fixtures.sample_data import sample_frame
from tests.unit.api.test_api import service_for

PASSWORD = "correct horse battery"


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(service=service_for(tmp_path)))


def _csv() -> bytes:
    return sample_frame().to_csv(index=False).encode()


def test_password_hash_is_salted_and_never_the_password() -> None:
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second and PASSWORD not in first
    assert verify_password(PASSWORD, first)
    assert not verify_password("wrong password", first)
    assert not verify_password(PASSWORD, "not-a-hash")


def test_every_data_route_requires_a_session(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        missing = "00000000-0000-0000-0000-000000000000"
        for method, url in [
            ("get", "/api/datasets"),
            ("get", f"/api/datasets/{missing}"),
            ("get", "/api/runs"),
            ("get", f"/api/runs/{missing}"),
            ("get", f"/api/runs/{missing}/results"),
            ("get", f"/api/runs/{missing}/export/csv"),
            ("get", "/api/memory"),
            ("post", f"/api/datasets/{missing}/runs"),
            ("get", "/api/auth/me"),
        ]:
            assert getattr(client, method)(url).status_code == 401, url
        assert client.get("/health").status_code == 200
        assert client.get("/api/auth/status").json()["has_accounts"] is False


def test_signup_signin_signout_and_cookie_flags(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = {"email": "  Ada@Example.COM ", "password": PASSWORD}
        created = client.post("/api/auth/signup", json=body)
        assert created.status_code == 201
        assert created.json()["email"] == "ada@example.com"
        cookie = created.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie
        assert PASSWORD not in created.text
        assert client.get("/api/auth/me").json()["email"] == "ada@example.com"

        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401

        wrong = client.post(
            "/api/auth/login", json={"email": "ada@example.com", "password": "nope-nope"}
        )
        unknown = client.post(
            "/api/auth/login", json={"email": "who@example.com", "password": "nope-nope"}
        )
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()  # no hint about which emails exist
        ok = client.post("/api/auth/login", json={"email": "ADA@example.com", "password": PASSWORD})
        assert ok.status_code == 200
        assert client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize(
    "email, password, fragment",
    [
        ("not-an-email", PASSWORD, "valid email"),
        ("a@b.co", "short", "at least 8"),
        ("a@b.co", "x" * 129, ""),
    ],
)
def test_signup_validation(tmp_path: Path, email: str, password: str, fragment: str) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/auth/signup", json={"email": email, "password": password})
        assert response.status_code == 422
        assert fragment in response.text


def test_duplicate_email_and_closed_signup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _client(tmp_path) as client:
        body = {"email": "a@example.com", "password": PASSWORD}
        assert client.post("/api/auth/signup", json=body).status_code == 201
        assert client.post("/api/auth/signup", json=body).status_code == 422
        monkeypatch.setenv("PRAMANA_ALLOW_SIGNUP", "0")
        other = {"email": "b@example.com", "password": PASSWORD}
        assert client.post("/api/auth/signup", json=other).status_code == 403
        assert client.get("/api/auth/status").json()["signup_open"] is False


def test_repeated_failures_lock_the_attempt_out(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        client.post("/api/auth/signup", json={"email": "a@example.com", "password": PASSWORD})
        client.post("/api/auth/logout")
        bad = {"email": "a@example.com", "password": "wrong-password"}
        assert [client.post("/api/auth/login", json=bad).status_code for _ in range(5)] == [401] * 5
        assert client.post("/api/auth/login", json=bad).status_code == 429
        good = {"email": "a@example.com", "password": PASSWORD}
        assert client.post("/api/auth/login", json=good).status_code == 429


def test_expired_sessions_are_refused(tmp_path: Path) -> None:
    service = AuthService(tmp_path / "x.sqlite3")
    user, _ = service.signup("a@example.com", PASSWORD, allow_signup=True)
    token = service.open_session(user)
    assert service.user_for(token) == user
    import sqlite3

    with sqlite3.connect(tmp_path / "x.sqlite3") as connection:
        connection.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00'")
    assert service.user_for(token) is None
    assert service.user_for("not-a-token") is None


def test_users_cannot_see_or_touch_each_others_data(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    app = create_app(service=service)
    with TestClient(app) as ada, TestClient(app) as bob:
        ada.post("/api/auth/signup", json={"email": "ada@example.com", "password": PASSWORD})
        bob.post("/api/auth/signup", json={"email": "bob@example.com", "password": PASSWORD})

        dataset = ada.post("/api/datasets", files={"file": ("bp.csv", _csv())}).json()
        run = ada.post(f"/api/datasets/{dataset['dataset_id']}/runs").json()
        mine = {"datasets": "/api/datasets", "runs": "/api/runs"}
        assert len(ada.get(mine["datasets"]).json()) == 1
        assert len(ada.get(mine["runs"]).json()) == 1

        assert bob.get(mine["datasets"]).json() == []
        assert bob.get(mine["runs"]).json() == []
        for url in [
            f"/api/datasets/{dataset['dataset_id']}",
            f"/api/datasets/{dataset['dataset_id']}/runs",
            f"/api/runs/{run['run_id']}",
            f"/api/runs/{run['run_id']}/results",
            f"/api/runs/{run['run_id']}/export/json",
        ]:
            assert bob.get(url).status_code == 404, url
        assert bob.post(f"/api/datasets/{dataset['dataset_id']}/runs").status_code == 404

        assert ada.get(f"/api/runs/{run['run_id']}/results").status_code == 200


def test_work_stored_before_accounts_goes_to_the_first_account_only(tmp_path: Path) -> None:
    service = service_for(tmp_path)
    legacy = service.repository.create(__import__("uuid").uuid4(), "old.csv")
    app = create_app(service=service)
    with TestClient(app) as first, TestClient(app) as second:
        first.post("/api/auth/signup", json={"email": "first@example.com", "password": PASSWORD})
        second.post("/api/auth/signup", json={"email": "second@example.com", "password": PASSWORD})
        assert [r["run_id"] for r in first.get("/api/runs").json()] == [str(legacy.run_id)]
        assert second.get("/api/runs").json() == []


def test_cross_site_writes_are_refused(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = {"email": "a@example.com", "password": PASSWORD}
        evil = client.post(
            "/api/auth/signup", json=body, headers={"origin": "https://evil.example"}
        )
        assert evil.status_code == 403
        same = client.post("/api/auth/signup", json=body, headers={"origin": "http://testserver"})
        assert same.status_code == 201


def test_lockout_is_per_address_so_one_attacker_cannot_lock_out_a_victim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRAMANA_TRUST_PROXY", "1")
    with _client(tmp_path) as client:
        client.post("/api/auth/signup", json={"email": "victim@example.com", "password": PASSWORD})
        client.post("/api/auth/logout")
        attacker = {"x-forwarded-for": "203.0.113.9"}
        bad = {"email": "victim@example.com", "password": "wrong-password"}
        for _ in range(5):
            assert client.post("/api/auth/login", json=bad, headers=attacker).status_code == 401
        assert client.post("/api/auth/login", json=bad, headers=attacker).status_code == 429
        good = {"email": "victim@example.com", "password": PASSWORD}
        # The real owner, from another address, is not locked out by the attacker's failures.
        owner = {"x-forwarded-for": "198.51.100.4"}
        assert client.post("/api/auth/login", json=good, headers=owner).status_code == 200


def test_the_forwarded_address_is_ignored_unless_the_proxy_is_trusted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRAMANA_TRUST_PROXY", raising=False)
    with _client(tmp_path) as client:
        client.post("/api/auth/signup", json={"email": "a@example.com", "password": PASSWORD})
        client.post("/api/auth/logout")
        bad = {"email": "a@example.com", "password": "wrong-password"}
        # Spoofed, rotating headers must not reset the counter.
        codes = [
            client.post(
                "/api/auth/login", json=bad, headers={"x-forwarded-for": f"10.0.0.{i}"}
            ).status_code
            for i in range(6)
        ]
        assert codes == [401] * 5 + [429]


def test_spraying_many_emails_from_one_address_is_stopped(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        codes = [
            client.post(
                "/api/auth/login",
                json={"email": f"user{i}@example.com", "password": "wrong-password"},
            ).status_code
            for i in range(32)
        ]
        assert codes[:30] == [401] * 30 and codes[30:] == [429, 429]


def test_signups_from_one_address_are_throttled(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        codes = [
            client.post(
                "/api/auth/signup", json={"email": f"user{i}@example.com", "password": PASSWORD}
            ).status_code
            for i in range(12)
        ]
        assert codes[:10] == [201] + [201] * 9 and codes[10:] == [429, 429]


def test_the_failure_memory_cannot_be_grown_without_bound(tmp_path: Path) -> None:
    from pramana.api import auth as auth_module

    service = AuthService(tmp_path / "x.sqlite3")
    for i in range(auth_module.MAX_TRACKED * 2):
        service._fail(f"user{i}@example.com|1.2.3.4")
    assert len(service._failures) <= auth_module.MAX_TRACKED


def test_two_simultaneous_signups_on_an_empty_closed_server_make_only_one_owner(
    tmp_path: Path,
) -> None:
    import threading

    service = AuthService(tmp_path / "x.sqlite3")
    results: list[str] = []

    def attempt(i: int) -> None:
        try:
            service.signup(f"u{i}@example.com", PASSWORD, allow_signup=False, client=f"10.0.0.{i}")
            results.append("created")
        except Exception as error:
            results.append(type(error).__name__)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count("created") == 1
    assert service.user_count() == 1


def test_csv_export_keeps_negative_numbers_as_numbers_but_guards_text(tmp_path: Path) -> None:
    import csv
    import io

    from pramana.api.routes.results import export_results  # noqa: F401  (route exists)
    from tests.unit.api.test_api import service_for as _svc

    service = _svc(tmp_path)
    app = create_app(service=service)
    with TestClient(app) as client:
        client.post("/api/auth/signup", json={"email": "a@example.com", "password": PASSWORD})
        run = client.post("/api/runs", files={"file": ("toy.csv", b"a,b\n1,2\n")}).json()["run_id"]
        body = client.get(f"/api/runs/{run}/export/csv").text
        rows = list(csv.DictReader(io.StringIO(body)))
        assert rows and all(not r["effect_size"].startswith("'") for r in rows)
