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
    if note.effect_metric is EffectMetric.MASE_REDUCTION:
        return (
            f" With {note.n_effective:,} blocks of backtest origins, a reduction of about "
            f"{note.detectable_effect * 100:.0f}% of the baseline's error or more would usually "
            f"have been found; a smaller one could be missed."
        )
    scale = note.effect_metric.value.replace("_", " ")
    return (
        f" With {note.n_effective:,} {note.unit}, an effect of about "
        f"{note.detectable_effect:.2f} ({scale}) or larger would usually have been found; "
        f"a smaller one could be missed."
    )


def _forecast_held_up(proof: ProofObject) -> str:
    """The sentence for a forecast claim that passed: past accuracy, never the next periods.

    Guarantees: says "held up in backtest", states the error reduction on periods the method did
    not see and how many further checks survived, says when the stated range is not calibrated,
    and always carries the proof's own limit sentence. Wording only: it never changes a verdict.
    """
    forecast = proof.forecast
    assert forecast is not None
    survived, ran = _checks(proof)
    baseline = "seasonal-naive" if forecast.baseline == "seasonal_naive" else "last-value"
    tried = (
        f"survived {survived} of {ran} further checks that could be run"
        if ran
        else "no further check could be run"
    )
    text = (
        f"Held up in backtest: the method's error was {forecast.error_reduction * 100:.0f}% "
        f"lower than a {baseline} forecast on {forecast.n_origins} backtest origins from periods "
        f"it did not see, and it {tried}."
    )
    if forecast.interval_calibrated is False and forecast.interval_coverage is not None:
        text += (
            f" Accuracy held up, but the stated range is not calibrated: it covered "
            f"{forecast.interval_coverage * 100:.0f}% of later periods, not "
            f"{(forecast.interval_level or 0) * 100:.0f}%."
        )
    return f"{text} {forecast.disclaimer}"


def _held_up(proof: ProofObject) -> str:
    """The sentence for a claim that passed: what was tried, what could not be judged, the limits.

    Guarantees: always states K of M, the checks that could be run (M = survived + broken);
    how many applicable checks could not tell; that only this table's columns were checked;
    and "little checked" when M is below `attacks.min_capacity`. Wording only: it never
    changes a verdict.
    """
    survived, ran = _checks(proof)
    unable = sum(a.outcome is AttackOutcome.NOT_RUN and a.applicable for a in proof.attacks)
    little = ran < load_verification_config().attacks.min_capacity
    tried = (
        f"survived {survived} of {ran} further checks that could be run"
        if ran
        else "no further check could be run"
    )
    text = (
        f"Passed the significance test after correction for multiple tests, but little was "
        f"checked: {tried}"
        if little
        else f"Held up: passed the significance test after correction for multiple tests and "
        f"{tried}"
    )
    if unable:
        text += f" ({unable} applicable {'check' if unable == 1 else 'checks'} could not tell)"
    return (
        text + ". Checked against the columns in this table only: an association in this data,"
        " not a causal conclusion."
    )


def _did_not_hold(proof: ProofObject) -> str:
    """The sentence for a PASS that a check broke: which check, how many held, what a break means.

    Guarantees: names the first check that broke the claim and says that a break is not proof
    the claim is false. Wording only: the FRAGILE verdict is the gateway's.
    """
    broken = next((a for a in proof.attacks if a.outcome is AttackOutcome.BROKEN), None)
    if broken is None:
        return "Passed the significance test, but did not hold under a further check."
    survived, ran = _checks(proof)
    reason = broken.reason.strip().rstrip(".")
    if proof.forecast is not None:
        return (
            f"The backtest passed the significance test, but the {broken.name.lower()} check "
            f"broke it: {reason[:1].lower() + reason[1:]}. {survived} of {ran} further checks "
            "that could be run survived. A broken check is not proof the forecast is bad: it "
            "means the backtest's advantage did not survive that check on these periods, so it "
            f"is not shown as a finding. {proof.forecast.disclaimer}"
        )
    return (
        f"Passed the significance test, but the {broken.name.lower()} check broke it: "
        f"{reason[:1].lower() + reason[1:]}. {survived} of {ran} further checks that could be "
        "run survived. A broken check is not proof the claim is false: it means the effect did "
        "not survive that check on these rows, so it is not shown as a finding."
    )


def rejection_reason(proof: ProofObject) -> str:
    """Explain an existing verdict without leaking provider errors or deciding it."""
    if (proof.failure_reason or "").startswith("generator unavailable"):
        return "The configured verifier is unavailable. Check its credentials and connection."
    forecast = proof.forecast is not None
    return {
        GateOutcome.SUPPORTED: _forecast_held_up(proof) if forecast else _held_up(proof),
        GateOutcome.REFUTED: (
            "The method was less accurate than the baseline on the periods it did not see."
            if forecast
            else "The observed direction does not support the proposed direction."
        ),
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
