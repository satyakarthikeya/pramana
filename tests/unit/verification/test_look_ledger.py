"""S7: a proof says how many earlier runs used the same held-back rows; nothing is blocked."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from pramana.contracts import DataStructure
from pramana.orchestration.verification_integration import gate_rows
from pramana.verification.looks import rows_key
from tests.fixtures.config import load_pinned_config

CONFIG = load_pinned_config()


def _table(seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"x": rng.normal(size=200), "y": rng.normal(size=200)})


def test_each_new_run_sees_how_many_others_used_the_same_rows(tmp_path: Path) -> None:
    db = tmp_path / "looks.sqlite3"
    structure = DataStructure.independent_rows()
    seen = []
    for _ in range(4):
        _, split = gate_rows(_table(), structure, CONFIG, run_id=uuid4(), looks_db=db)
        seen.append(split.prior_looks)
        assert split.look_budget == CONFIG.dependence.max_prior_looks
    assert seen == [0, 1, 2, 3]


def test_a_retry_of_the_same_run_is_not_a_second_look(tmp_path: Path) -> None:
    db = tmp_path / "looks.sqlite3"
    run = uuid4()
    structure = DataStructure.independent_rows()
    first = gate_rows(_table(), structure, CONFIG, run_id=run, looks_db=db)[1]
    again = gate_rows(_table(), structure, CONFIG, run_id=run, looks_db=db)[1]
    assert first.prior_looks == again.prior_looks == 0


def test_another_table_starts_at_zero(tmp_path: Path) -> None:
    db = tmp_path / "looks.sqlite3"
    structure = DataStructure.independent_rows()
    gate_rows(_table(1), structure, CONFIG, run_id=uuid4(), looks_db=db)
    other = gate_rows(_table(2), structure, CONFIG, run_id=uuid4(), looks_db=db)[1]
    assert other.prior_looks == 0


def test_no_ledger_means_no_disclosure_and_the_same_rows(tmp_path: Path) -> None:
    structure = DataStructure.independent_rows()
    with_ledger_rows, _ = gate_rows(
        _table(), structure, CONFIG, run_id=uuid4(), looks_db=tmp_path / "l.sqlite3"
    )
    plain_rows, plain_split = gate_rows(_table(), structure, CONFIG)
    assert plain_split.prior_looks is None
    pd.testing.assert_frame_equal(with_ledger_rows, plain_rows)


def test_a_ledger_that_cannot_be_opened_never_stops_a_run(tmp_path: Path) -> None:
    structure = DataStructure.independent_rows()
    blocked = tmp_path / "a-file"
    blocked.write_text("not a directory")
    rows, split = gate_rows(_table(), structure, CONFIG, run_id=uuid4(), looks_db=blocked / "db")
    assert len(rows) > 0 and split.prior_looks is None


def test_key_changes_with_content() -> None:
    a = _table(1)
    b = a.copy()
    b.loc[0, "x"] += 1.0
    assert rows_key(a) == rows_key(a.copy()) and rows_key(a) != rows_key(b)
