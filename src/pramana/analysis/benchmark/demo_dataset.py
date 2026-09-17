"""Deterministic demo dataset construction for the analysis-to-verification path."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


DEMO_COLUMNS = (
    "age",
    "gender",
    "race",
    "time_in_hospital",
    "num_lab_procedures",
    "num_medications",
    "number_outpatient",
    "number_emergency",
    "number_inpatient",
    "number_diagnoses",
    "readmitted",
    "injected_false_signal",
)


def create_demo_dataset(
    output_path: str | Path = "data/interim/pramana_demo.csv",
    *,
    rows: int = 120,
    seed: int = 20260817,
) -> Path:
    """Write a demo frame with a real relationship and an independent noise pair."""

    if rows < 20:
        raise ValueError("rows must be at least 20 for the verification gateway")
    rng = np.random.default_rng(seed)
    age = rng.integers(18, 70, size=rows)
    bmi = 18 + age * 0.12 + rng.normal(0, 2, size=rows)
    frame = pd.DataFrame(
        {
            "age": age,
            "bmi": bmi,
            "noise_a": rng.normal(size=rows),
            "noise_b": rng.normal(size=rows),
            "region": rng.choice(["north", "south"], size=rows),
        }
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path.resolve()


def build_demo_from_diabetes(
    source_dir: str | Path,
    output_path: str | Path = "data/demo/pramana_diabetes_demo.csv",
    *,
    rows: int = 1000,
    seed: int = 20260817,
) -> Path:
    """Build a bounded demo with real hospital variables and one known noise signal.

    The source file is never modified. The returned CSV contains a reproducible
    sample with the source marginals preserved and an independently shuffled
    numeric column labelled ``injected_false_signal``.
    """

    if not 500 <= rows <= 2000:
        raise ValueError("rows must be between 500 and 2000 for the demo dataset")
    source = Path(source_dir) / "diabetic_data.csv"
    if not source.is_file():
        raise FileNotFoundError(f"expected diabetes source file at {source}")

    source_frame = pd.read_csv(
        source,
        na_values=["?", "NA", "N/A", "NULL", "null"],
        keep_default_na=True,
        low_memory=False,
    )
    required = set(DEMO_COLUMNS) - {"injected_false_signal"}
    missing = sorted(required - set(source_frame.columns))
    if missing:
        raise ValueError(f"source dataset is missing required columns: {missing}")

    rng = np.random.default_rng(seed)
    frame = source_frame.loc[:, list(required)].copy()
    frame = frame.dropna(subset=["age", "gender", "time_in_hospital", "num_lab_procedures"])
    if len(frame) < rows:
        raise ValueError(f"source has only {len(frame)} usable rows; {rows} are required")
    frame = frame.sample(n=rows, random_state=seed).reset_index(drop=True)
    shuffled = frame["num_lab_procedures"].to_numpy(copy=True)
    rng.shuffle(shuffled)
    frame["injected_false_signal"] = shuffled
    frame = frame.loc[:, DEMO_COLUMNS]

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path.resolve()
