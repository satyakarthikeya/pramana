"""Product presentation helpers; verification remains gateway-owned."""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pramana.common.config import load_config
from pramana.contracts import EffectMetric, GateOutcome, ProofObject
from pramana.verification.config import load_config as load_verification_config


class V1Settings(BaseModel):
    """Validate product runtime budgets without altering the gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    generator: Literal["template", "llm"]
    max_candidates: int = Field(ge=1, le=50)
    preview_rows: int = Field(ge=1, le=10)


def v1_settings() -> V1Settings:
    """Load V1 limits from their single product configuration."""
    return load_config("v1", V1Settings)


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
        GateOutcome.NOT_TESTABLE: _untested_reason(proof),
        GateOutcome.FRAGILE: (
            proof.failure_reason
            or "Passed the gate but did not survive a falsification attack."
        ),
    }[proof.gate_outcome]


#: Refusals whose text came from somewhere a user should not read verbatim (generated
#: code errors, provider messages); every other NOT_TESTABLE reason is written for users.
_INTERNAL_REASONS = ("no falsification program could be generated", "generator unavailable")


def _untested_reason(proof: ProofObject) -> str:
    reason = (proof.failure_reason or "").strip()
    if reason and not reason.startswith(_INTERNAL_REASONS):
        return reason[0].upper() + reason[1:]
    return "The claim could not be tested under the supported safety rules."



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
