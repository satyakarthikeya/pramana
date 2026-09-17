"""`ProofObject` -- the gateway's output, and the only thing downstream may trust.

Three invariants are enforced by the model itself rather than by the code that builds
it, because a rule that lives in the builder is a rule the next builder can forget:

1. **PASS iff SUPPORTED** (AGENTS.md 0). A `PASS` on a refuted, negligible,
   inconclusive or untestable claim is unconstructable. The memory guard checks the
   verdict; this makes the verdict impossible to set dishonestly in the first place.
2. **Null exactly when untested.** A screened-out claim carries no statistics -- a
   `p_value` of 1.0 on a claim nothing ran would be a fabricated number, and a
   conservative-looking fabrication is still a fabrication. Conversely a tested claim
   must carry all of them: AGENTS.md 3.6 says there is no such thing as a partial
   proof object.
3. **Scores rank findings, not non-findings.** `evidence_score` is present exactly
   for `SUPPORTED` claims, so nothing downstream can sort a rejected claim into a
   list of results by giving it a number.

A crashed or timed-out test is NOT a screening: code was generated and did run, so
the audit trail and the family membership both survive, and the p-value is the most
conservative available (1.0) rather than absent.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 1
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pramana.contracts.enums import Direction, EffectMetric, GateOutcome, TestType, Verdict

#: Fields that only exist because a test was executed. Null exactly when the claim
#: was screened out before any code was generated.
_STATISTICAL_FIELDS: tuple[str, ...] = (
    "p_value",
    "q_value",
    "effect_size",
    "effect_metric",
    "test_type",
    "falsification_code",
    "n_hypotheses_in_batch",
)

#: Also computed from the data, but optional for a tested claim: a metric may have no
#: signed direction, and not every template reports a second, human-readable effect.
_OPTIONAL_STATISTICAL_FIELDS: tuple[str, ...] = (
    "reported_effect",
    "reported_effect_metric",
    "observed_direction",
)


class ScoreComponents(BaseModel):
    """The legs of the evidence score, kept so a score can be explained, not just cited.

    `s_q` is the significance leg, `s_e` the effect leg, `s_r` the stability leg.
    All three are normalised to [0, 1], which is what makes their geometric mean a
    score where the weakest leg caps the result.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    s_q: float = Field(ge=0.0, le=1.0, description="Significance leg.")
    s_e: float = Field(ge=0.0, le=1.0, description="Effect-size leg.")
    s_r: float = Field(ge=0.0, le=1.0, description="Stability leg.")


class ProofObject(BaseModel):
    """The complete, immutable record of one verdict.

    Guarantees: frozen, no unknown fields, and the three invariants above hold for
    every instance that exists -- there is no valid way to build one that breaks them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- identity ---------------------------------------------------------
    insight_id: str = Field(min_length=1)
    verdict: Verdict
    gate_outcome: GateOutcome
    bh_family_id: str = Field(
        min_length=1,
        description="Which BH family this claim belongs to, or was excluded from. "
        "Reviewers will ask what was corrected together; this answers it.",
    )
    seed: int = Field(description="The run seed, logged so the test can be re-run (AGENTS.md 3.4).")

    # --- statistics: null exactly when the claim was never tested ---------
    p_value: float | None = Field(default=None, ge=0.0, le=1.0)
    q_value: float | None = Field(default=None, ge=0.0, le=1.0, description="BH-corrected.")
    effect_size: float | None = Field(default=None, description="In the gating metric's units.")
    effect_metric: EffectMetric | None = Field(default=None, description="What was gated on.")
    test_type: TestType | None = None
    falsification_code: str | None = Field(
        default=None, description="The code that actually ran -- the audit trail."
    )
    n_hypotheses_in_batch: int | None = Field(
        default=None, ge=1, description="Size of the BH family. Null for a screened-out claim."
    )

    # --- reporting extras -------------------------------------------------
    reported_effect: float | None = Field(
        default=None, description="A second effect in units a reader can act on."
    )
    reported_effect_metric: str | None = None
    asserted_direction: Direction | None = Field(
        default=None, description="What the claim said. Copied from the candidate."
    )
    observed_direction: Direction | None = Field(
        default=None, description="What the data showed. Null for an unsigned metric."
    )
    outlier_warning: bool = Field(
        default=False, description="The result moved materially when outliers were trimmed."
    )

    # --- scoring and failure ----------------------------------------------
    evidence_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Present exactly for SUPPORTED claims."
    )
    score_components: ScoreComponents | None = None
    failure_reason: str | None = Field(
        default=None,
        description="Why the claim was screened out, or how the test failed. Written for "
        "the analysis agent to act on.",
    )

    @field_validator("bh_family_id", "insight_id")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        """The three invariants, checked in a fixed order.

        Order matters: the verdict/outcome contradiction is reported first, so a proof
        that is wrong in several ways names the prime-directive violation rather than
        a downstream symptom of it.
        """
        self._check_verdict_matches_outcome()
        self._check_null_exactly_when_untested()
        self._check_score_belongs_to_a_finding()
        return self

    def _check_verdict_matches_outcome(self) -> None:
        passed = self.verdict is Verdict.PASS
        supported = self.gate_outcome is GateOutcome.SUPPORTED
        if passed != supported:
            raise ValueError(
                f"verdict {self.verdict.value!r} contradicts gate_outcome "
                f"{self.gate_outcome.value!r}: PASS is valid for "
                f"{GateOutcome.SUPPORTED.value!r} and for nothing else (AGENTS.md 0)"
            )

    def _check_null_exactly_when_untested(self) -> None:
        untested = self.gate_outcome is GateOutcome.NOT_TESTABLE
        if untested:
            populated = [
                name
                for name in (*_STATISTICAL_FIELDS, *_OPTIONAL_STATISTICAL_FIELDS)
                if getattr(self, name) is not None
            ]
            if populated:
                raise ValueError(
                    f"{populated} must be null on a {GateOutcome.NOT_TESTABLE.value!r} claim: "
                    f"nothing was executed, so any value there was fabricated"
                )
            if not (self.failure_reason or "").strip():
                raise ValueError(
                    f"a {GateOutcome.NOT_TESTABLE.value!r} claim must carry a failure_reason "
                    f"saying why, so the analysis agent can rewrite the claim"
                )
            return

        missing = [name for name in _STATISTICAL_FIELDS if getattr(self, name) is None]
        if missing:
            raise ValueError(
                f"{missing} must be populated on a tested claim: there is no such thing as a "
                f"partial proof object (AGENTS.md 3.6)"
            )

    def _check_score_belongs_to_a_finding(self) -> None:
        supported = self.gate_outcome is GateOutcome.SUPPORTED
        if supported and self.evidence_score is None:
            raise ValueError(
                f"a {GateOutcome.SUPPORTED.value!r} claim must carry an evidence_score"
            )
        if not supported and self.evidence_score is not None:
            raise ValueError(
                f"evidence_score must be null on a {self.gate_outcome.value!r} claim: a scored "
                f"non-finding invites someone ranking it as a finding"
            )
        if self.score_components is not None and self.evidence_score is None:
            raise ValueError("score_components without an evidence_score has nothing to explain")
