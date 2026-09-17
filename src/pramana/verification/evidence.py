"""The gate and the evidence score -- two different jobs, deliberately kept apart.

**The gate decides. The score only ranks.** Collapsing them is tempting and would
quietly forfeit the FDR guarantee: if a claim could pass by scoring highly overall, a
large effect would buy its way past a q-value that Benjamini-Hochberg says is noise.
So the verdict is a hard conjunction --

    q < alpha   AND   |effect| >= the metric's floor   AND   direction matches

-- and the score is computed only for claims that already passed, purely to order them
in a report. Nothing gates on the score. `configs/verification.yaml` accordingly has no
global evidence threshold: a config key that nothing reads is one a reader assumes is
load-bearing.

Why four outcomes instead of a boolean
--------------------------------------
`Verdict` is binary because the memory guard needs one boolean (AGENTS.md 0). But
"REJECT" answers the wrong question for the analysis agent, which needs to know whether
to rewrite the claim or drop it:

  * `NEGLIGIBLE` -- real but too small to be a finding. The claim is true and boring.
  * `REFUTED`    -- significant and strong, pointing the OTHER WAY. The data actively
                    contradicts the sentence; reversing it would be a real finding.
  * `INCONCLUSIVE` -- not significant after correction. Nothing was learned.

Why the score is a geometric mean
---------------------------------
`(s_q * s_e * s_r)^(1/3)`. An arithmetic mean lets a strong effect average away a
marginal q-value; the geometric mean lets the WEAKEST leg cap the result, and a zero on
any leg zeroes the score. That matches what the legs mean -- they are not
interchangeable currencies, they are three things that all have to hold.

Why the significance leg is logarithmic
---------------------------------------
On a linear scale every strong claim scores ~1.0 and the score stops discriminating
exactly where a reader most wants an ordering. `log(alpha/q) / log(alpha/floor)` spends
its range across orders of magnitude instead, and it saturates at the PERMUTATION
FLOOR (`1/(B+1)`) rather than at zero -- because zero is not a p-value any finite
number of resamples can produce, and pretending otherwise would let a claim score 1.0
for precision the test never had.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 4
"""

from __future__ import annotations

import math
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pramana.contracts.enums import Direction, EffectMetric, GateOutcome, Verdict
from pramana.contracts.proof_object import ScoreComponents
from pramana.verification.config import EffectBand, EvidenceConfig

#: Metrics whose sign carries meaning, so an observed direction exists to check against
#: the claim. The others answer "do these differ?", a question with no direction:
#: epsilon-squared is a variance ratio and Cramer's V a normalised chi-square, and both
#: are non-negative by construction.
SIGNED_METRICS: frozenset[EffectMetric] = frozenset(
    {EffectMetric.SPEARMAN_RHO, EffectMetric.KENDALL_TAU_B, EffectMetric.CLIFFS_DELTA}
)

#: Metrics reported as a squared quantity, gated on their square root so the band sits
#: on the same scale as a correlation. eps^2 = 0.02 looks negligible against a 0.10
#: floor, but its root is 0.14 -- a rho-equivalent that clears it honestly.
ROOT_GATED_METRICS: frozenset[EffectMetric] = frozenset({EffectMetric.EPSILON_SQUARED})

#: The stability leg when nothing measured it. 1.0 is neutral under a geometric mean:
#: it neither rewards nor penalises a claim whose stability was never assessed.
DEFAULT_STABILITY = 1.0


class GateDecision(BaseModel):
    """What the gate concluded about one claim, and everything behind the conclusion.

    Guarantees, mirroring `ProofObject` so the gateway cannot build an inconsistent
    proof from a consistent decision: `verdict is PASS` exactly when `outcome is
    SUPPORTED`, and `evidence_score` is non-null exactly then too.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: GateOutcome
    verdict: Verdict
    evidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    score_components: ScoreComponents | None = None
    observed_direction: Direction | None = Field(
        default=None, description="Sign of the effect. Null for an unsigned metric."
    )
    min_effect: float = Field(
        description="The floor this claim was actually held to, after any metric-specific "
        "scaling. Recorded because it is not always the raw configured band."
    )
    gated_effect: float = Field(
        description="The effect as compared against `min_effect` -- a magnitude, and a "
        "square root for the root-gated metrics."
    )

    @model_validator(mode="after")
    def _score_belongs_to_a_pass(self) -> Self:
        supported = self.outcome is GateOutcome.SUPPORTED
        if (self.verdict is Verdict.PASS) != supported:
            raise ValueError(
                f"verdict {self.verdict.value!r} contradicts outcome {self.outcome.value!r}"
            )
        if supported != (self.evidence_score is not None):
            raise ValueError("an evidence_score exists exactly for a SUPPORTED outcome")
        return self


def significance_leg(q_value: float, alpha: float, p_value_floor: float) -> float:
    """How far past alpha the evidence reaches, on a log scale, normalised to [0, 1].

    `log(alpha/q) / log(alpha/floor)`: zero at and above alpha, 1.0 at the permutation
    floor, and spread across the orders of magnitude in between.

    Guarantees: monotone decreasing in `q_value`; exactly 0.0 at and above alpha, so a
    claim that failed the gate cannot pick up score from this leg; exactly 1.0 at (or
    below) the floor. Raises on a non-positive q -- p-values are add-one floored, so a
    zero means something upstream fabricated a number.
    """
    if q_value <= 0.0:
        raise ValueError(
            f"q_value must be positive; got {q_value}. A permutation p-value is floored "
            f"at 1/(B+1), so zero did not come from the vetted stats library."
        )
    if not 0.0 < p_value_floor < alpha:
        raise ValueError(
            f"need 0 < p_value_floor < alpha for the significance leg to be defined; "
            f"got floor={p_value_floor}, alpha={alpha}"
        )
    if q_value >= alpha:
        return 0.0
    return min(1.0, math.log(alpha / q_value) / math.log(alpha / p_value_floor))


def effect_leg(effect_size: float, min_effect: float, strong_effect: float) -> float:
    """Where the effect sits between "not negligible" and "strong", in [0, 1].

    Linear between the two ends and clipped at both: an effect exactly at the floor
    scores 0.0 (it only just cleared the gate -- it should rank last, not be rewarded),
    and everything at or beyond `strong_effect` scores 1.0 rather than running away
    with the ranking.

    Guarantees: monotone non-decreasing in `|effect_size|`. Uses the MAGNITUDE; whether
    the sign is acceptable is the direction check's job, not the score's.
    """
    if not min_effect < strong_effect:
        raise ValueError(
            f"need min_effect < strong_effect; got {min_effect} and {strong_effect}"
        )
    span = (abs(effect_size) - min_effect) / (strong_effect - min_effect)
    return max(0.0, min(1.0, span))


def evidence_score(s_q: float, s_e: float, s_r: float = DEFAULT_STABILITY) -> float:
    """Combine the three normalised legs into one number for RANKING.

    The geometric mean `(s_q * s_e * s_r)^(1/3)`, so the weakest leg caps the score and
    a zero anywhere zeroes it. This number never decides a verdict.

    Guarantees: in [0, 1], monotone non-decreasing in each leg, and 0.0 if any leg is
    0.0. Raises if a leg was not normalised first -- an un-normalised leg would silently
    change what the geometric mean means.
    """
    for name, leg in (("s_q", s_q), ("s_e", s_e), ("s_r", s_r)):
        if not 0.0 <= leg <= 1.0:
            raise ValueError(f"{name} must be normalised to [0, 1]; got {leg}")
    return float((s_q * s_e * s_r) ** (1.0 / 3.0))


def _band_for(
    effect_metric: EffectMetric, config: EvidenceConfig, table_k: int | None
) -> EffectBand:
    """The band this metric is held to, after any metric-specific scaling.

    Cramer's V is the only metric whose floor depends on the data's shape: V is
    normalised by `min(rows, cols) - 1`, so a bigger contingency table reaches a given V
    with weaker per-cell association. Holding a 5x5 table to the same 0.10 as a 2x2
    would let large tables pass trivially, so the band is divided by `sqrt(k - 1)`.
    Both ends scale together, keeping the band's shape.

    Fails closed on a metric with no band rather than passing a claim with no check
    applied -- though `EvidenceConfig` already refuses to load in that state, so this
    is the second of two locks.
    """
    if not isinstance(effect_metric, EffectMetric):
        raise ValueError(
            f"{effect_metric!r} is not one of the vetted gating metrics; the gate fails "
            f"closed rather than applying no threshold at all"
        )
    try:
        band = config.threshold_for(effect_metric)
    except KeyError as missing:  # pragma: no cover -- config load already guarantees this
        raise ValueError(
            f"no effect threshold configured for {effect_metric.value!r}; refusing to "
            f"gate a claim with no band"
        ) from missing

    if effect_metric is not EffectMetric.CRAMERS_V:
        return band
    if table_k is None:
        raise ValueError(
            "Cramer's V needs the table size k = min(rows, cols) to scale its threshold; "
            "a fixed cutoff would let large contingency tables pass trivially"
        )
    if table_k < 2:
        raise ValueError(f"table_k must be at least 2; got {table_k}")
    scale = math.sqrt(table_k - 1)
    return EffectBand(min=band.min / scale, strong=band.strong / scale)


def _observed_direction(effect_size: float, effect_metric: EffectMetric) -> Direction | None:
    """The sign of the effect, or None when the metric has no sign to read."""
    if effect_metric not in SIGNED_METRICS or effect_size == 0.0:
        return None
    return Direction.POSITIVE if effect_size > 0.0 else Direction.NEGATIVE


def evaluate_gate(
    *,
    q_value: float,
    effect_size: float,
    effect_metric: EffectMetric,
    alpha: float,
    p_value_floor: float,
    config: EvidenceConfig,
    asserted_direction: Direction | None = None,
    stability: float = DEFAULT_STABILITY,
    table_k: int | None = None,
) -> GateDecision:
    """Decide one claim's outcome, then score it only if it survived.

    The checks run in a fixed order, and the order encodes what each rejection means:

    1. **Significance.** `q < alpha`, STRICTLY -- a q sitting exactly on alpha is not
       evidence. Fails to `INCONCLUSIVE`: nothing was learned, and no statement about
       the effect is warranted.
    2. **Magnitude.** `|effect| >= the metric's floor`, inclusively -- a claim exactly
       at the floor passes the gate and scores 0.0 on the effect leg. Fails to
       `NEGLIGIBLE` (AGENTS.md 3.5: a tiny p with a negligible effect is not a finding).
    3. **Direction.** Only when the claim asserted one AND the metric has a sign.
       Fails to `REFUTED` -- the data contradicts the sentence as written, which is a
       different thing from having learned nothing.

    Guarantees: `PASS` is returned exactly for `SUPPORTED`, and an evidence score exists
    exactly then. The score never influences any of the three checks. Raises rather than
    guessing when a metric has no band, when Cramer's V arrives without its table size,
    or when `effect_size` is not finite -- NaN compares False against everything, so
    without this check it would pass the magnitude test it never took. The executor
    refuses such a payload first; this is the second lock, for any caller that reaches
    the gate without going through the executor.
    """
    if not math.isfinite(effect_size):
        raise ValueError(
            f"effect_size is {effect_size!r}, which is not a finite number. Every comparison "
            f"against a NaN is False, so a NaN would sail past the magnitude check and be "
            f"clamped to a full effect leg; the gate refuses to decide on it instead."
        )
    band = _band_for(effect_metric, config, table_k)
    gated_effect = (
        math.sqrt(abs(effect_size))
        if effect_metric in ROOT_GATED_METRICS
        else abs(effect_size)
    )
    observed = _observed_direction(effect_size, effect_metric)
    rejected = {
        "min_effect": band.min,
        "gated_effect": gated_effect,
        "observed_direction": observed,
        "verdict": Verdict.REJECT,
    }

    if q_value >= alpha:
        return GateDecision(outcome=GateOutcome.INCONCLUSIVE, **rejected)  # type: ignore[arg-type]
    if gated_effect < band.min:
        return GateDecision(outcome=GateOutcome.NEGLIGIBLE, **rejected)  # type: ignore[arg-type]
    contradicted = (
        asserted_direction is not None
        and observed is not None
        and observed is not asserted_direction
    )
    if contradicted:
        return GateDecision(outcome=GateOutcome.REFUTED, **rejected)  # type: ignore[arg-type]

    components = ScoreComponents(
        s_q=significance_leg(q_value, alpha, p_value_floor),
        s_e=effect_leg(gated_effect, band.min, band.strong),
        s_r=stability,
    )
    return GateDecision(
        outcome=GateOutcome.SUPPORTED,
        verdict=Verdict.PASS,
        evidence_score=evidence_score(components.s_q, components.s_e, components.s_r),
        score_components=components,
        observed_direction=observed,
        min_effect=band.min,
        gated_effect=gated_effect,
    )
