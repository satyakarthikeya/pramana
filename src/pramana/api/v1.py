"""Product presentation helpers; verification remains gateway-owned."""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pramana.common.config import load_config
from pramana.contracts import AttackOutcome, EffectMetric, GateOutcome, ProofObject
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


def _checks(proof: ProofObject) -> tuple[int, int]:
    """(checks survived, checks that ran) among the attacks; not-run ones count for neither."""
    ran = [a for a in proof.attacks if a.outcome is not AttackOutcome.NOT_RUN]
    return sum(a.outcome is AttackOutcome.SURVIVED for a in ran), len(ran)


def _could_detect(proof: ProofObject) -> str:
    """The power note as a sentence: what the rows could have found, never a verdict."""
    note = proof.power
    if note is None:
        return ""
    scale = note.effect_metric.value.replace("_", " ")
    return (
        f" With {note.n_effective:,} {note.unit}, an effect of about "
        f"{note.detectable_effect:.2f} ({scale}) or larger would usually have been found; "
        f"a smaller one could be missed."
    )


def _held_up(proof: ProofObject) -> str:
    """The sentence for a claim that passed: what was tried, what could not be judged, the limits.

    Guarantees: states K of M checks that ran, how many applicable checks could not tell, that
    only this table's columns were checked, and "little checked" when fewer than
    `attacks.min_capacity` checks ran. Wording only: it never changes a verdict.
    """
    survived, ran = _checks(proof)
    unable = sum(a.outcome is AttackOutcome.NOT_RUN and a.applicable for a in proof.attacks)
    little = ran < load_verification_config().attacks.min_capacity
    text = (
        "Passed the significance test after correction for multiple tests, but little was "
        "checked"
        if little
        else "Held up: passed the significance test after correction for multiple tests"
    )
    if ran:
        text += f" and survived {survived} of {ran} further checks"
    elif little:
        text += ": no further check could be run"
    if unable:
        text += f" ({unable} could not tell)"
    return (
        text + ". Checked against the columns in this table only: an association in this data,"
        " not a causal conclusion."
    )


def _did_not_hold(proof: ProofObject) -> str:
    broken = next((a for a in proof.attacks if a.outcome is AttackOutcome.BROKEN), None)
    if broken is None:
        return "Passed the significance test, but did not hold under a further check."
    reason = broken.reason.strip()
    return (
        f"Passed the significance test, but did not hold under the {broken.name.lower()} "
        f"check: {reason[:1].lower() + reason[1:]}"
    )


def rejection_reason(proof: ProofObject) -> str:
    """Explain an existing verdict without leaking provider errors or deciding it."""
    if (proof.failure_reason or "").startswith("generator unavailable"):
        return "The configured verifier is unavailable. Check its credentials and connection."
    return {
        GateOutcome.SUPPORTED: _held_up(proof),
        GateOutcome.REFUTED: "The observed direction does not support the proposed direction.",
        GateOutcome.NEGLIGIBLE: (
            "Unlikely to be chance, but the effect is below the minimum size that counts as "
            "meaningful, so it is not reported as a finding."
        ),
        GateOutcome.INCONCLUSIVE: (
            "The test could not run successfully; this claim is not verified."
            if proof.failure_reason
            else "Not enough evidence at this sample size after correction for multiple "
            "tests, so it is not shown as a finding. That does not mean the claim is false."
            + _could_detect(proof)
        ),
        GateOutcome.NOT_TESTABLE: _untested_reason(proof),
        GateOutcome.FRAGILE: _did_not_hold(proof),
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
