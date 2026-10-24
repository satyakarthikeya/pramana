"""A per-table count of earlier runs that tested on the same held-back rows (design v3, S7).

Every run on a table is judged on the same held-back half. The more runs have looked at
those rows (and chosen what to ask next after seeing earlier answers), the less they act
like fresh data. This ledger counts, per held-back rows content, how many OTHER runs used
them, so a proof can say so. It only counts and discloses: it never blocks a run, changes
a verdict or touches the family. A time-ordered split cannot be redrawn (the latest
periods always confirm), so disclosure is the response there.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pandas as pd


def rows_key(rows: pd.DataFrame) -> str:
    """A content fingerprint of the held-back rows (values and column names)."""
    hashed = pd.util.hash_pandas_object(rows, index=False).to_numpy().tobytes()
    names = "\x1f".join(map(str, rows.columns)).encode("utf-8")
    return hashlib.sha256(names + hashed).hexdigest()


def record_look(db: Path, key: str, run_id: str) -> int:
    """Record that `run_id` tested on `key`; return how many OTHER runs already had.

    Idempotent per (key, run): a retry of the same run is not a second look.
    """
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db, timeout=10) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS looks ("
            "rows_key TEXT NOT NULL, run_id TEXT NOT NULL, PRIMARY KEY (rows_key, run_id))"
        )
        (others,) = conn.execute(
            "SELECT COUNT(*) FROM looks WHERE rows_key = ? AND run_id != ?", (key, run_id)
        ).fetchone()
        conn.execute("INSERT OR IGNORE INTO looks (rows_key, run_id) VALUES (?, ?)", (key, run_id))
    return int(others)
