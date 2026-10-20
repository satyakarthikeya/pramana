"""Publish cleaned frames using the existing shared worker artifact convention."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID, uuid4

import pandas as pd

from pramana.common.paths import DATA_DIR


def persist_cleaned_dataset(
    frame: pd.DataFrame, run_id: UUID | str, *, data_dir: Path | None = None
) -> str:
    """Return a worker-loadable path to the exact cleaned frame for this run.

    Guarantees: dtypes, index and missing values survive pandas pickle round-trip;
    the final file becomes visible only after serialization finishes; a published
    run artifact is never overwritten. An identical retry reuses it, while different
    values or dtypes for the same run raise. Concurrent publishers cannot replace
    each other's file. Publication errors propagate; no raw-data fallback exists.

    The root must be shared at the same path by producer and worker. Pickles are
    internal artifacts only, never accepted as dataset uploads. This uses the same
    runs/<UUID>/cleaned.pkl layout the native verification handler already enforces.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("cleaned dataset must be a pandas DataFrame")
    identifier = UUID(str(run_id))
    root = (data_dir or DATA_DIR).resolve()
    runs_dir = root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    if not runs_dir.resolve().is_relative_to(root):
        raise ValueError("cleaned artifact must remain inside the shared data directory")
    run_dir = runs_dir / str(identifier)
    run_dir.mkdir(parents=True, exist_ok=True)
    if not run_dir.resolve().is_relative_to(root):
        raise ValueError("cleaned artifact must remain inside the shared data directory")
    target = run_dir / "cleaned.pkl"
    if target.is_symlink():
        raise ValueError("cleaned artifact must not be a symbolic link")
    temporary = run_dir / f".cleaned.{uuid4().hex}.tmp"
    try:
        frame.to_pickle(temporary)
        try:
            # A hard link publishes a complete file without replacing an existing one.
            os.link(temporary, target)
        except FileExistsError:
            # Pickle bytes can differ for equivalent copies (pandas block layout).
            # Compare the actual frame exactly, rather than its serialization bytes.
            existing = pd.read_pickle(target)
            try:
                pd.testing.assert_frame_equal(existing, frame, check_exact=True)
                if existing.attrs != frame.attrs:
                    raise AssertionError("cleaned dataframe attributes differ")
            except AssertionError:
                raise ValueError(
                    "different cleaned data is already published for this run"
                ) from None
        return str(target.resolve())
    finally:
        temporary.unlink(missing_ok=True)
