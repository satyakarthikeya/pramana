"""Chat over the API: ownership, fail-closed behaviour, the testing ledger, and the real gateway."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pramana.analysis.workspace import load_workspace_config
from pramana.api.main import create_app
from pramana.common.llm_client import ChatMessage, Completion
from tests.fixtures.sample_data import SAMPLE_ROWS, sample_frame
from tests.unit.api.test_api import service_for, sign_in

CLAIM = {
    "action": "test",
    "claim": {
        "claim_type": "correlation",
        "variables": ["age_years", "systolic_bp"],
        "direction": "positive",
        "reference_group": None,
    },
}
DESCRIBE = {"action": "tool", "tool": "describe", "args": {"column": "age_years"}}


class Script:
    """Replies in order; the same list serves every question asked through one service."""

    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)

    def __call__(self, messages: Sequence[ChatMessage]) -> Completion:
        reply = self.replies.pop(0)
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return Completion(content=text, input_tokens=400, output_tokens=40)


def _upload(client: TestClient) -> str:
    csv = sample_frame().to_csv(index=False).encode()
    return client.post("/api/datasets", files={"file": ("bp.csv", csv)}).json()["dataset_id"]


def _client(tmp_path: Path, script: Script | None, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # The offline reference generator; a live DeepSeek call is never made by the suite.
    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "template")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    return TestClient(create_app(service=service_for(tmp_path, chat=script)))


def test_a_descriptive_question_is_answered_stored_and_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = Script(
        DESCRIBE, {"action": "answer", "text": "500 ages are recorded.", "cites": ["x1"]}
    )
    with _client(tmp_path, script, monkeypatch) as client:
        sign_in(client)
        dataset = _upload(client)
        reply = client.post(f"/api/datasets/{dataset}/chat", json={"question": "how many ages?"})
        assert reply.status_code == 200
        body = reply.json()
        assert body["answer"]["kind"] == "descriptive"
        assert body["answer"]["evidence"][0]["output"]["n"] == SAMPLE_ROWS
        history = client.get(f"/api/datasets/{dataset}/chat").json()
        assert [h["question"] for h in history] == ["how many ages?"]
        assert history[0]["message_id"] == body["message_id"]
        ledger = client.get(f"/api/datasets/{dataset}/chat/tests").json()
        assert ledger["chat_tests"] == 0 and ledger["records"] == []


def test_a_claim_goes_through_the_real_gateway_and_is_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service_script = Script(CLAIM, CLAIM)
    with _client(tmp_path, service_script, monkeypatch) as client:
        sign_in(client)
        dataset = _upload(client)
        first = client.post(
            f"/api/datasets/{dataset}/chat",
            json={"question": "does age_years relate to systolic_bp?"},
        )
        answer = first.json()["answer"]
        # The planted age/blood-pressure relationship must pass the real permutation test.
        assert answer["kind"] == "verified", answer["text"]
        proof = answer["tested"]["row"]["proof"]
        assert proof["verdict"] == "PASS" and proof["q_value"] < 0.05
        assert answer["tested"]["disclosure"] == {
            "test_number": 1,
            "earlier_chat_tests": 0,
            "earlier_run_tests": 0,
            "family_size": 1,
            "asked_after_seeing_results": True,
            "corrected_for_earlier_tests": False,
        }
        assert "not corrected" in answer["text"]
        second = client.post(
            f"/api/datasets/{dataset}/chat", json={"question": "again: age_years and systolic_bp?"}
        ).json()
        assert second["answer"]["tested"]["disclosure"]["test_number"] == 2
        assert second["answer"]["tested"]["disclosure"]["earlier_chat_tests"] == 1
        ledger = client.get(f"/api/datasets/{dataset}/chat/tests").json()
        assert ledger["chat_tests"] == 2 and ledger["limit"] > 2
        assert [r["test_number"] for r in ledger["records"]] == [1, 2]
        assert ledger["records"][0]["label"] == "verified"


def test_chat_never_writes_to_verified_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = service_for(tmp_path, chat=Script(CLAIM))
    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "template")
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        dataset = _upload(client)
        reply = client.post(
            f"/api/datasets/{dataset}/chat", json={"question": "age_years and systolic_bp?"}
        )
        assert reply.json()["answer"]["kind"] == "verified"
        assert service.store.browse(limit=100) == []
        assert client.get("/api/memory").json() == []


def test_a_busy_verifier_means_the_claim_is_not_tested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = service_for(tmp_path, chat=Script(CLAIM))
    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "template")
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        dataset = _upload(client)
        assert service.reserve()  # an analysis run holds the only slot
        try:
            reply = client.post(
                f"/api/datasets/{dataset}/chat", json={"question": "age_years and systolic_bp?"}
            )
        finally:
            service.release()
        answer = reply.json()["answer"]
        assert answer["kind"] == "not_tested" and "Nothing was marked verified" in answer["text"]
        assert client.get(f"/api/datasets/{dataset}/chat/tests").json()["chat_tests"] == 0
        assert service.reserve()  # the slot was handed back, not leaked
        service.release()


def test_without_a_model_chat_fails_closed_and_stores_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRAMANA_CHAT_ENGINE", "model")
    with _client(tmp_path, None, monkeypatch) as client:
        sign_in(client)
        dataset = _upload(client)
        reply = client.post(f"/api/datasets/{dataset}/chat", json={"question": "hello?"})
        assert reply.status_code == 503
        assert "DEEPSEEK_API_KEY" in reply.json()["detail"] and "sk-" not in reply.text
        assert client.get(f"/api/datasets/{dataset}/chat").json() == []


def test_another_account_cannot_read_ask_or_count_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _client(tmp_path, Script(CLAIM), monkeypatch) as client:
        sign_in(client, "owner@example.com")
        dataset = _upload(client)
        client.post(
            f"/api/datasets/{dataset}/chat", json={"question": "age_years and systolic_bp?"}
        )
        client.cookies.clear()
        sign_in(client, "stranger@example.com")
        base = f"/api/datasets/{dataset}/chat"
        assert client.get(base).status_code == 404
        assert client.get(base + "/tests").status_code == 404
        assert client.post(base, json={"question": "hi"}).status_code == 404
        client.cookies.clear()
        assert client.get(base).status_code == 401
        sign_in(client, "owner@example.com")
        assert len(client.get(base).json()) == 1


def test_bad_questions_and_unknown_datasets_are_refused_plainly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _client(tmp_path, Script(), monkeypatch) as client:
        sign_in(client)
        dataset = _upload(client)
        base = f"/api/datasets/{dataset}/chat"
        assert client.post(base, json={"question": ""}).status_code == 422
        assert client.post(base, json={"question": "   "}).status_code == 422
        too_long = "x" * (load_workspace_config().chat.max_question_chars + 1)
        long_reply = client.post(base, json={"question": too_long})
        assert long_reply.status_code == 422 and "characters" in long_reply.json()["detail"]
        missing = "00000000-0000-0000-0000-000000000000"
        assert (
            client.post(f"/api/datasets/{missing}/chat", json={"question": "hi"}).status_code == 404
        )


def test_the_hourly_cap_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_workspace_config()
    capped = config.model_copy(
        update={"chat": config.chat.model_copy(update={"max_messages_per_hour": 1})}
    )
    monkeypatch.setattr("pramana.chat.service.load_workspace_config", lambda: capped)
    answer = {"action": "answer", "text": "This table has no column about income.", "cites": []}
    with _client(tmp_path, Script(answer, answer), monkeypatch) as client:
        sign_in(client)
        dataset = _upload(client)
        base = f"/api/datasets/{dataset}/chat"
        assert client.post(base, json={"question": "one"}).status_code == 200
        limited = client.post(base, json={"question": "two"})
        assert limited.status_code == 429 and "limit" in limited.json()["detail"]


def test_a_row_saved_by_an_older_version_is_shown_as_unreadable_not_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _client(tmp_path, Script(), monkeypatch) as client:
        sign_in(client)
        dataset = _upload(client)
        with sqlite3.connect(tmp_path / "api/runs.sqlite3") as db:
            owner_id = db.execute("SELECT owner_id FROM datasets").fetchone()[0]
            db.execute(
                "INSERT INTO chat_exchanges VALUES (?,?,?,?,?)",
                (
                    "11111111-1111-1111-1111-111111111111",
                    dataset,
                    owner_id,
                    "2026-01-01T00:00:00+00:00",
                    json.dumps({"question": "an old question", "answer": {"legacy": True}}),
                ),
            )
        history = client.get(f"/api/datasets/{dataset}/chat").json()
        assert history[0]["question"] == "an old question"
        assert history[0]["answer"]["kind"] == "unanswered"
        assert "older version" in history[0]["answer"]["text"]


# ---- reviewer regressions: concurrency, slot handling and trace binding ----------------------
def _capped(monkeypatch: pytest.MonkeyPatch, **chat: int) -> None:
    config = load_workspace_config()
    capped = config.model_copy(update={"chat": config.chat.model_copy(update=chat)})
    monkeypatch.setattr("pramana.chat.service.load_workspace_config", lambda: capped)


def test_parallel_questions_cannot_beat_the_hourly_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reviewer's C7: the cap used to be checked before and written after a slow answer."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from uuid import UUID

    from pramana.chat.service import ChatRateLimited

    _capped(monkeypatch, max_messages_per_hour=1)
    answer = json.dumps({"action": "answer", "text": "No.", "cites": []})

    def slow(_messages: Sequence[ChatMessage]) -> Completion:
        time.sleep(0.4)
        return Completion(content=answer, input_tokens=10, output_tokens=5)

    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "template")
    service = service_for(tmp_path, chat=slow)
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        dataset = UUID(_upload(client))
        owner = UUID(client.get("/api/auth/me").json()["user_id"])
        outcomes: list[str] = []
        lock = threading.Lock()

        def one() -> None:
            try:
                service.chat.ask(dataset, owner, "anything")
                result = "answered"
            except ChatRateLimited:
                result = "limited"
            with lock:
                outcomes.append(result)

        with ThreadPoolExecutor(6) as pool:
            for _ in range(6):
                pool.submit(one)
        assert sorted(outcomes) == ["answered"] + ["limited"] * 5


def test_ledger_numbers_stay_unique_when_writers_collide(tmp_path: Path) -> None:
    """The reviewer's C8: a test that already ran must still be counted, never lost."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import UTC, datetime
    from uuid import uuid4

    from pramana.chat.models import LedgerRecord
    from pramana.chat.store import ChatRepository

    repository = ChatRepository(tmp_path / "chat.sqlite3")
    dataset, owner = uuid4(), uuid4()

    def record(number: int) -> LedgerRecord:
        return LedgerRecord(
            test_number=number,
            message_id=uuid4(),
            created_at=datetime.now(UTC),
            question="q",
            claim="c",
            label="rejected",
        )

    with ThreadPoolExecutor(8) as pool:
        saved = list(
            pool.map(lambda _i: repository.add_next_test(record, dataset, owner), range(24))
        )
    assert sorted(r.test_number for r in saved) == list(range(1, 25))
    assert [r.test_number for r in repository.tests(dataset, owner)] == list(range(1, 25))


def test_the_per_dataset_test_limit_stops_further_gateway_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _capped(monkeypatch, max_tests_per_dataset=1)
    with _client(tmp_path, Script(CLAIM, CLAIM), monkeypatch) as client:
        sign_in(client)
        dataset = _upload(client)
        base = f"/api/datasets/{dataset}/chat"
        question = {"question": "does age_years relate to systolic_bp?"}
        assert client.post(base, json=question).json()["answer"]["kind"] == "verified"
        second = client.post(base, json=question).json()["answer"]
        assert second["kind"] == "not_tested" and "limit" in second["text"]
        assert client.get(base + "/tests").json()["chat_tests"] == 1


def test_the_run_slot_is_handed_back_after_a_crashing_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object) -> object:
        raise RuntimeError("sk-secret-key participant-name")

    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "template")
    service = service_for(tmp_path, chat=Script(CLAIM), chat_verifier=broken)
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        dataset = _upload(client)
        reply = client.post(
            f"/api/datasets/{dataset}/chat",
            json={"question": "does age_years relate to systolic_bp?"},
        )
        assert reply.status_code == 200 and reply.json()["answer"]["kind"] == "not_tested"
        assert "sk-secret" not in reply.text and "participant" not in reply.text
        assert service.reserve(), "the slot must not leak when the verifier crashes"
        service.release()


def test_the_model_written_test_code_is_traced_under_the_message_uuid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The llm generator reads its trace id from logging context; chat must set it."""
    seen: list[str] = []

    def spy(*_args: object, **kwargs: object) -> object:
        seen.append(str(kwargs["run_id"]))
        raise RuntimeError("no network in tests")

    monkeypatch.setattr("pramana.verification.falsification.generator.complete_chat", spy)
    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "llm")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "not-a-real-key")
    service = service_for(tmp_path, chat=Script(CLAIM))
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        dataset = _upload(client)
        reply = client.post(
            f"/api/datasets/{dataset}/chat",
            json={"question": "does age_years relate to systolic_bp?"},
        ).json()
    assert seen == [reply["message_id"]]
    assert reply["answer"]["kind"] == "not_tested"
    assert "Nothing was marked verified" in reply["answer"]["text"]


def test_a_non_significant_chat_claim_is_not_described_as_corrected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A chat test is a family of one, so 'after correction for multiple tests' would be false."""
    from pramana.contracts import GateOutcome
    from tests.unit.memory.test_store import _proof

    def inconclusive(candidate, _frame, _message_id):  # noqa: ANN001
        return _proof(candidate.insight_id, GateOutcome.INCONCLUSIVE)

    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "template")
    service = service_for(tmp_path, chat=Script(CLAIM), chat_verifier=inconclusive)
    with TestClient(create_app(service=service)) as client:
        sign_in(client)
        dataset = _upload(client)
        reply = client.post(
            f"/api/datasets/{dataset}/chat",
            json={"question": "does age_years relate to systolic_bp?"},
        ).json()["answer"]
    assert reply["kind"] == "rejected"
    assert "single test" in reply["text"] and "after correction" not in reply["text"]
    assert "single test" in reply["tested"]["row"]["explanation"]
