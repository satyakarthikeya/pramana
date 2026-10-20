"""V1 presentation and deterministic sample; verification remains gateway-owned."""

from __future__ import annotations

import math
import re
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.benchmark.demo_dataset import DemoSpec, inject_false_correlation
from pramana.common.config import load_config
from pramana.contracts import EffectMetric, GateOutcome, ProofObject
from pramana.verification.config import load_config as load_verification_config


class V1Settings(BaseModel):
    """Validate product runtime and sample budgets without altering the gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    generator: Literal["template", "llm"]
    max_candidates: int = Field(ge=1, le=50)
    preview_rows: int = Field(ge=1, le=10)
    sample_seed: int
    sample_rows: int = Field(ge=500, le=2000)
    sample_pilot_rows: int = Field(ge=30, le=100)
    sample_decoy_rho: float = Field(gt=0, lt=1)


def v1_settings() -> V1Settings:
    """Load V1 limits from their single product configuration."""
    return load_config("v1", V1Settings)


def sample_frame() -> pd.DataFrame:
    """Build reproducible synthetic measurements, not real participant data."""
    settings = v1_settings()
    rng = np.random.default_rng(settings.sample_seed)
    age = rng.uniform(20, 80, settings.sample_rows)
    frame = pd.DataFrame(
        {
            "age_years": age,
            "systolic_bp": 80 + age * 0.8 + rng.normal(0, 4, settings.sample_rows),
            "noise_measurement": rng.normal(size=settings.sample_rows),
            "constant_column": np.ones(settings.sample_rows),
        }
    )
    spec = DemoSpec(
        seed=settings.sample_seed,
        n_rows=settings.sample_rows,
        min_age_years=20,
        decoy_column="moon_phase_pilot",
        decoy_target="age_years",
        decoy_pilot_rows=settings.sample_pilot_rows,
        decoy_target_rho=settings.sample_decoy_rho,
    )
    return inject_false_correlation(frame, spec)[0]


def rejection_reason(proof: ProofObject) -> str:
    """Explain an existing verdict without leaking provider errors or deciding it."""
    if (proof.failure_reason or "").startswith("generator unavailable"):
        return "The configured verifier is unavailable. Check its credentials and connection."
    return {
        GateOutcome.SUPPORTED: "Supported on this dataset; not a causal conclusion.",
        GateOutcome.REFUTED: "The observed direction does not support the proposed direction.",
        GateOutcome.NEGLIGIBLE: "The effect is below the configured meaningful-effect floor.",
        GateOutcome.INCONCLUSIVE: (
            "The test could not run successfully; this claim is not verified."
            if proof.failure_reason
            else "Not statistically significant after correction for multiple tests."
        ),
        GateOutcome.NOT_TESTABLE: "The claim could not be tested under the supported safety rules.",
    }[proof.gate_outcome]


def effect_strength(proof: ProofObject) -> str | None:
    """Label existing configured bands; never introduce another gating threshold."""
    if proof.effect_size is None or proof.effect_metric is None:
        return None
    config = load_verification_config()
    bands = config.evidence.effect_thresholds[proof.effect_metric]
    effect = abs(proof.effect_size)
    if proof.effect_metric is EffectMetric.EPSILON_SQUARED:
        effect = math.sqrt(effect)
    return "small" if effect < bands.min else "medium" if effect < bands.strong else "large"


def permutation_count(proof: ProofObject) -> int | None:
    """Read the stored program's declared count, not today's configuration."""
    match = re.search(r"^N_PERMUTATIONS\s*=\s*(\d+)\s*$", proof.falsification_code or "", re.M)
    return int(match[1]) if match else None
