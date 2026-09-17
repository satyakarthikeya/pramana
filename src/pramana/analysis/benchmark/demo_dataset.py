"""Small deterministic integration dataset for the analysis-to-verification path."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


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
