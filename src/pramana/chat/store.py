"""Conversations and the testing ledger, stored per user and dataset beside run metadata.

The ledger is the count of claims chat has sent to the gateway on a dataset. It exists so no
test goes uncounted: each chat claim is tested on its own, so the honest way to read its
q-value is next to how many tests came before it.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from pramana.chat.models import ChatAnswer, ChatExchange, ChatWork, LedgerRecord

_UNREADABLE = "This message was saved by an older version of PRAMANA and cannot be shown."


class ChatRepository:
    """SQLite persistence; every read is filtered by owner, so ids never cross accounts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS chat_exchanges (
                message_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                created_at TEXT NOT NULL, exchange_json TEXT NOT NULL)""")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS chat_by_dataset "
                "ON chat_exchanges (dataset_id, owner_id)"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS chat_tests (
                message_id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                test_number INTEGER NOT NULL, created_at TEXT NOT NULL, record_json TEXT NOT NULL,
                UNIQUE (dataset_id, test_number))""")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    # ---- conversation ---------------------------------------------------------------
    @staticmethod
    def _load(raw: str, message_id: str, dataset_id: str) -> ChatExchange:
        """Read a saved exchange; one written by an older version is shown as unreadable."""
        try:
            return ChatExchange.model_validate_json(raw)
        except ValidationError:
            try:
                question = str(json.loads(raw).get("question", ""))[:4000] or "(unreadable)"
            except (ValueError, AttributeError):
                question = "(unreadable)"
            return ChatExchange(
                message_id=UUID(message_id),
                dataset_id=UUID(dataset_id),
                created_at=datetime.now(UTC),
                question=question,
                answer=ChatAnswer(
                    kind="unanswered",
                    text=_UNREADABLE,
                    work=ChatWork(
                        turns=0, tool_calls=0, examined=0, input_tokens=0, output_tokens=0
                    ),
                ),
            )

    def add_exchange(self, exchange: ChatExchange, owner_id: UUID) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO chat_exchanges "
                "(message_id, dataset_id, owner_id, created_at, exchange_json) VALUES (?,?,?,?,?)",
                (
                    str(exchange.message_id),
                    str(exchange.dataset_id),
                    str(owner_id),
                    exchange.created_at.isoformat(),
                    exchange.model_dump_json(),
                ),
            )

    def history(self, dataset_id: UUID, owner_id: UUID, limit: int = 200) -> list[ChatExchange]:
        """Oldest first, so the conversation reads top to bottom."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT message_id, exchange_json FROM chat_exchanges "
                "WHERE dataset_id = ? AND owner_id = ? ORDER BY rowid DESC LIMIT ?",
                (str(dataset_id), str(owner_id), limit),
            ).fetchall()
        return [self._load(raw, mid, str(dataset_id)) for mid, raw in reversed(rows)]

    def recent_questions(self, dataset_id: UUID, owner_id: UUID, count: int) -> list[str]:
        """The user's own earlier questions. Earlier model answers are never reused as context."""
        if count <= 0:
            return []
        return [item.question for item in self.history(dataset_id, owner_id, limit=count)]

    def messages_since(self, owner_id: UUID, hours: int = 1) -> int:
        """How many questions this account asked recently, for the hourly cap."""
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM chat_exchanges WHERE owner_id = ? AND created_at >= ?",
                (str(owner_id), cutoff),
            ).fetchone()
        return int(row[0])

    # ---- testing ledger -------------------------------------------------------------
    def test_count(self, dataset_id: UUID, owner_id: UUID) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM chat_tests WHERE dataset_id = ? AND owner_id = ?",
                (str(dataset_id), str(owner_id)),
            ).fetchone()
        return int(row[0])

    def add_test(self, record: LedgerRecord, dataset_id: UUID, owner_id: UUID) -> None:
        """Record one gateway test. The unique number makes a double count impossible."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO chat_tests "
                "(message_id, dataset_id, owner_id, test_number, created_at, record_json) "
                "VALUES (?,?,?,?,?,?)",
                (
                    str(record.message_id),
                    str(dataset_id),
                    str(owner_id),
                    record.test_number,
                    record.created_at.isoformat(),
                    record.model_dump_json(),
                ),
            )

    def add_next_test(
        self,
        make: Callable[[int], LedgerRecord],
        dataset_id: UUID,
        owner_id: UUID,
    ) -> LedgerRecord:
        """Record a test under the next free number, chosen inside one write transaction.

        `BEGIN IMMEDIATE` takes the database's write lock before the number is read, so two
        writers can never pick the same number and a test that already ran is always counted.
        """
        connection = self._connect()
        connection.isolation_level = None  # explicit transaction control
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(test_number), 0) FROM chat_tests WHERE dataset_id = ?",
                (str(dataset_id),),
            ).fetchone()
            record = make(int(row[0]) + 1)
            connection.execute(
                "INSERT INTO chat_tests "
                "(message_id, dataset_id, owner_id, test_number, created_at, record_json) "
                "VALUES (?,?,?,?,?,?)",
                (
                    str(record.message_id),
                    str(dataset_id),
                    str(owner_id),
                    record.test_number,
                    record.created_at.isoformat(),
                    record.model_dump_json(),
                ),
            )
            connection.execute("COMMIT")
            return record
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def tests(self, dataset_id: UUID, owner_id: UUID) -> list[LedgerRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM chat_tests WHERE dataset_id = ? AND owner_id = ? "
                "ORDER BY test_number",
                (str(dataset_id), str(owner_id)),
            ).fetchall()
        records = []
        for (raw,) in rows:
            try:
                records.append(LedgerRecord.model_validate_json(raw))
            except ValidationError:
                continue  # a row from a different version is skipped, never fatal
        return records
