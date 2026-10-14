"""Shared fixtures for the evaluation harness tests.

Thresholds, seeds and the schedule are always read from the shipped configs; the only
things changed are the dataset size and the resample count, for speed.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pramana.evaluation.config import EvaluationConfig, load_evaluation_config
from pramana.evaluation.planted import synthetic_extract
from pramana.verification.config import VerificationConfig
from tests.fixtures.config import load_pinned_config

#: Small enough for the gateway tests to stay quick, large enough for calibration to land.
TEST_ROWS = 400

#: Reduced resamples, still at the config's own lower bound (`ge=1000`).
TEST_PERMUTATIONS = 1000


@pytest.fixture(scope="session")
def eval_config() -> EvaluationConfig:
    shipped = load_evaluation_config()
    return shipped.model_copy(
        update={"extract_shape": shipped.extract_shape.model_copy(update={"n_rows": TEST_ROWS})}
    )


@pytest.fixture(scope="session")
def ver_config() -> VerificationConfig:
    """Pinned to the template generator, with fewer resamples."""
    pinned = load_pinned_config()
    return pinned.model_copy(
        update={
            "statistics": pinned.statistics.model_copy(
                update={"n_permutations": TEST_PERMUTATIONS}
            )
        }
    )


@pytest.fixture(scope="session")
def extract(eval_config: EvaluationConfig) -> tuple[pd.DataFrame, list[str]]:
    return synthetic_extract(eval_config.extract_shape, seed=7)
