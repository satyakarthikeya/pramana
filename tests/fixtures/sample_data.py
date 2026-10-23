"""Reproducible synthetic measurements for tests and acceptance scripts only.

This is test data, not a product feature: the application ships no sample dataset and no
sample endpoint. It is deterministic and holds no participant data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pramana.analysis.benchmark.demo_dataset import DemoSpec, inject_false_correlation

SAMPLE_SEED = 20261020
SAMPLE_ROWS = 500
SAMPLE_PILOT_ROWS = 40
SAMPLE_DECOY_RHO = 0.20


def sample_frame() -> pd.DataFrame:
    """A true age/blood-pressure relationship, a noise column, a constant, and a small decoy."""
    rng = np.random.default_rng(SAMPLE_SEED)
    age = rng.uniform(20, 80, SAMPLE_ROWS)
    frame = pd.DataFrame(
        {
            "age_years": age,
            "systolic_bp": 80 + age * 0.8 + rng.normal(0, 4, SAMPLE_ROWS),
            "noise_measurement": rng.normal(size=SAMPLE_ROWS),
            "constant_column": np.ones(SAMPLE_ROWS),
        }
    )
    spec = DemoSpec(
        seed=SAMPLE_SEED,
        n_rows=SAMPLE_ROWS,
        min_age_years=20,
        decoy_column="moon_phase_pilot",
        decoy_target="age_years",
        decoy_pilot_rows=SAMPLE_PILOT_ROWS,
        decoy_target_rho=SAMPLE_DECOY_RHO,
    )
    return inject_false_correlation(frame, spec)[0]
