"""A separate process must see the exact cleaned data, never an incomplete file."""

from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from pramana.analysis import handlers
from pramana.analysis.dataset_artifacts import persist_cleaned_dataset


def frame() -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "count": pd.Series([1, None, 3], dtype="Int64"),
            "label": pd.Series(["b", "a", None], dtype="category"),
            "date": pd.to_datetime(["2026-01-01", None, "2026-01-03"], utc=True),
            "text": pd.Series(["x", None, "z"], dtype="string"),
        }
    )
    result.index = pd.Index([4, 8, 12], name="source_row")
    result.attrs["cleaned"] = True
    return result


def test_separate_python_process_loads_exact_values_and_dtypes(tmp_path: Path) -> None:
    expected = frame()
    run_id = uuid4()
    reference = persist_cleaned_dataset(expected, run_id, data_dir=tmp_path)
    assert Path(reference) == tmp_path / "runs" / str(run_id) / "cleaned.pkl"
    worker_copy = tmp_path / "worker.pkl"
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import pandas as pd; pd.read_pickle(sys.argv[1]).to_pickle(sys.argv[2])",
            reference,
            str(worker_copy),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    actual = pd.read_pickle(worker_copy)
    pd.testing.assert_frame_equal(actual, expected)
    assert actual.attrs == expected.attrs


def test_identical_retry_reuses_file_and_changed_data_is_refused(tmp_path: Path) -> None:
    expected = frame()
    run_id = uuid4()
    reference = persist_cleaned_dataset(expected, run_id, data_dir=tmp_path)
    before = Path(reference).read_bytes()
    assert persist_cleaned_dataset(expected.copy(), str(run_id), data_dir=tmp_path) == reference
    changed = expected.copy()
    changed.loc[4, "count"] = 99
    with pytest.raises(ValueError, match="already published"):
        persist_cleaned_dataset(changed, run_id, data_dir=tmp_path)
    assert Path(reference).read_bytes() == before
    assert list(Path(reference).parent.glob("*.tmp")) == []


def test_different_runs_do_not_overwrite_each_other(tmp_path: Path) -> None:
    first = persist_cleaned_dataset(frame(), uuid4(), data_dir=tmp_path)
    second = persist_cleaned_dataset(frame(), uuid4(), data_dir=tmp_path)
    assert first != second
    pd.testing.assert_frame_equal(pd.read_pickle(first), pd.read_pickle(second))


def test_concurrent_identical_publishers_reuse_one_complete_file(tmp_path: Path) -> None:
    run_id = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: persist_cleaned_dataset(frame(), run_id, data_dir=tmp_path), range(2)
            )
        )
    assert results[0] == results[1]
    pd.testing.assert_frame_equal(pd.read_pickle(results[0]), frame())
    assert list(Path(results[0]).parent.glob("*.tmp")) == []


def test_failed_serialization_never_publishes_a_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_frame: pd.DataFrame, target: Path) -> None:
        target.write_bytes(b"partial")
        raise OSError("serialization failed")

    monkeypatch.setattr(pd.DataFrame, "to_pickle", fail)
    run_id = uuid4()
    with pytest.raises(OSError, match="serialization failed"):
        persist_cleaned_dataset(frame(), run_id, data_dir=tmp_path)
    assert list((tmp_path / "runs" / str(run_id)).iterdir()) == []


def test_failed_publication_propagates_and_cleans_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_source: Path, _target: Path) -> None:
        raise OSError("publication failed")

    monkeypatch.setattr("pramana.analysis.dataset_artifacts.os.link", fail)
    run_id = uuid4()
    with pytest.raises(OSError, match="publication failed"):
        persist_cleaned_dataset(frame(), run_id, data_dir=tmp_path)
    assert list((tmp_path / "runs" / str(run_id)).iterdir()) == []


def test_invalid_run_id_is_refused_before_creating_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        persist_cleaned_dataset(frame(), "../../other-run", data_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_preparation_cannot_fall_back_to_raw_reference_on_publication_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object) -> str:
        raise OSError("shared volume unavailable")

    monkeypatch.setattr(handlers, "persist_cleaned_dataset", fail)
    with pytest.raises(OSError, match="shared volume unavailable"):
        handlers.prepare({"run_id": uuid4(), "dataset": frame(), "dataset_ref": "raw.csv"})
