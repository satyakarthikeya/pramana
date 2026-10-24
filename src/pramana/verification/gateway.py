"""The gateway orchestrator: a batch of candidates in, a proof object each out.

    screen -> generate -> execute -> collect every p-value -> BH once -> gate -> proof

This module wires the pieces and owns none of their internals. The statistics live in
`stats/`, the correction in `fdr.py`, the decision in `evidence.py`, the sandbox in
`executor/`, and the code generation in `falsification/`. What belongs here, and
nowhere else, is the BATCH: which claims form the family, in what order the results
come back, and what happens to a claim at each way it can fail.

Why the whole batch goes through together
-----------------------------------------
Benjamini-Hochberg is a statement about a FAMILY of hypotheses, not about one
(AGENTS.md 3.2). Correcting per insight would mean correcting nothing at all: with one
p-value, BH returns it unchanged. So every admissible claim is tested first, all raw
p-values are collected, and `apply_bh` runs exactly once over the lot. One invocation
of `verify_batch` is one run is one family (docs/OPEN_ISSUES.md 1).

The three shapes a proof object comes in
----------------------------------------
1. **Tested.** Code was generated, it ran, it produced a stamped result. Full
   statistics, a q-value from the family correction, and a gate outcome.
2. **Executed but failed.** Code was generated and did run, then crashed, timed out,
   or returned something the executor refused. This is NOT a screening: the audit
   trail exists and the claim stays in the family, so it gets `p_value = 1.0` -- the
   most conservative value available rather than an absent one -- and INCONCLUSIVE.
3. **Never tested.** The admissibility screen refused the claim, or no falsification
   program could be generated for it. No code, no statistics, no family membership:
   NOT_TESTABLE with a reason the analysis agent can act on. A `p_value` of 1.0 here
   would be a fabricated number, and a conservative-looking fabrication is still one.

Keeping 2 and 3 distinct matters. Collapsing them would either invent statistics for a
claim nothing ran, or drop the audit trail for code that did.

Fail-closed, everywhere
-----------------------
There is no path in this module from any failure to `Verdict.PASS`. A PASS is
constructable only from a `SUPPORTED` gate decision, and `ProofObject` itself refuses
any other combination (AGENTS.md 0). Every `except` here ends in a REJECT.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 7
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from pramana.contracts.attack import AttackOutcome
from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import (
    ClaimType,
    EffectMetric,
    GateOutcome,
    Verdict,
)
from pramana.contracts.proof_object import ProofObject
from pramana.contracts.structure import DataStructure, SplitRecord
from pramana.verification.admissibility import screen
from pramana.verification.attacks import ClaimView, run_attacks
from pramana.verification.config import VerificationConfig
from pramana.verification.evidence import evaluate_gate
from pramana.verification.executor.runner import COLUMN_POLICY_REASON_PREFIX, execute
from pramana.verification.falsification import templates
from pramana.verification.falsification.generator import (
    FalsificationProgram,
    GeneratorError,
    GeneratorUnavailable,
    generate_from_template,
    get_generator,
)
from pramana.verification.fdr import apply_bh
from pramana.verification.interval import effect_interval
from pramana.verification.power import power_note
from pramana.verification.refuter import suggest_hints
from pramana.verification.spec import declared_permutations, spec_hash
from pramana.verification.schemes import (
    FREE_PLAN,
    PERIOD_COLUMN,
    TestPlan,
    assign_plan,
    with_period_column,
)

_log = logging.getLogger(__name__)

#: A test that did not produce a result gets the most conservative p-value there is.
#: Not absent: code ran, so the claim is part of the family and its failure must not
#: make every other claim's correction easier.
_FAILED_P_VALUE = 1.0

#: And no effect. Zero is the honest value for "nothing was measured", and it also
#: cannot clear any configured floor, so the outcome cannot come out SUPPORTED.
_FAILED_EFFECT_SIZE = 0.0

#: The gating metric each claim type WOULD have used, for the audit trail on a test
#: that failed before it could report one. A tested claim must name the metric it was
#: gated on (AGENTS.md 3.6), and this is the metric its template gates on. The value
#: beside it is 0.0 and the outcome is INCONCLUSIVE regardless, so this labels the
#: record without influencing any decision. `GROUP_DIFFERENCE` maps to the two-group
#: metric because the k-group case is only distinguishable by running the test.
_METRIC_BY_CLAIM_TYPE: dict[ClaimType, EffectMetric] = {
    ClaimType.CORRELATION: EffectMetric.SPEARMAN_RHO,
    ClaimType.TREND: EffectMetric.KENDALL_TAU_B,
    ClaimType.GROUP_DIFFERENCE: EffectMetric.CLIFFS_DELTA,
    ClaimType.PERIOD_CHANGE: EffectMetric.RELATIVE_CHANGE,
    ClaimType.SEASONALITY: EffectMetric.EPSILON_SQUARED,
}

#: Prefix on every family identifier, so the string is self-describing in a log line.
_FAMILY_PREFIX = "bh"

#: Enough hash to be unique across a project's runs, short enough to read.
_FAMILY_DIGEST_LENGTH = 12

#: Called as `generate(candidate, config)` for a free shuffle, and as
#: `generate(candidate, config, plan)` when the rows need a dependence-aware null, so a
#: two-argument generator still serves independent rows and fails closed on the rest.
Generator = Callable[..., FalsificationProgram]


def _emit(event: str, insight_id: str, **fields: Any) -> None:
    """One structured log line, always carrying `insight_id` (AGENTS.md 5).

    Uses the standard library directly because `pramana.common.logging` is another
    member's module and is still a stub; the JSON shape here matches the executor's,
    so the two read as one stream. When the shared configuration lands this should
    call it rather than format its own records.
    """
    _log.info(json.dumps({"event": event, "insight_id": insight_id, **fields}))


def _family_id(candidates: Sequence[CandidateInsight]) -> str:
    """A stable identifier for the set of claims corrected together.

    Guarantees: the same SET of insight IDs always produces the same identifier,
    regardless of the order they arrive in, and any change to the membership produces
    a different one. Reviewers ask what was corrected together; this is what answers
    it, and it has to survive being asked twice.
    """
    joined = "\n".join(sorted(candidate.insight_id for candidate in candidates))
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return f"{_FAMILY_PREFIX}-{digest[:_FAMILY_DIGEST_LENGTH]}"


def _require_unique_ids(candidates: Sequence[CandidateInsight]) -> None:
    """Refuse a batch that would produce two proofs under one key.

    Callers index proofs by `insight_id`. A duplicate would silently overwrite one
    verdict with another rather than reporting both, and the claim that vanished would
    be the one nobody notices.
    """
    seen: set[str] = set()
    duplicates: list[str] = []
    for candidate in candidates:
        if candidate.insight_id in seen:
            duplicates.append(candidate.insight_id)
        seen.add(candidate.insight_id)
    if duplicates:
        raise ValueError(
            f"insight_id must be unique within a run; repeated: {sorted(set(duplicates))}"
        )


def _not_testable(
    candidate: CandidateInsight,
    family_id: str,
    seed: int,
    reason: str,
    split: SplitRecord | None = None,
) -> ProofObject:
    """A claim nothing ran on: no statistics, no family membership, and a reason.

    Every statistical field stays null. The claim is excluded from the BH family and
    from `n_hypotheses_in_batch`, because the family is the TESTED set -- counting
    refusals would inflate the correction and make every real claim harder to pass for
    no statistical reason (docs/OPEN_ISSUES.md 5).
    """
    return ProofObject(
        insight_id=candidate.insight_id,
        verdict=Verdict.REJECT,
        gate_outcome=GateOutcome.NOT_TESTABLE,
        bh_family_id=family_id,
        seed=seed,
        asserted_direction=candidate.asserted_direction,
        failure_reason=reason,
        split=split,
    )


class _Tested:
    """One claim that reached the executor, holding what the gate will need.

    A small mutable carrier rather than a model: it exists only between execution and
    correction, never leaves this module, and never becomes output.
    """

    __slots__ = ("candidate", "program", "payload", "failure_reason", "plan")

    def __init__(
        self,
        candidate: CandidateInsight,
        program: FalsificationProgram,
        payload: dict[str, Any] | None,
        failure_reason: str | None,
        plan: TestPlan = FREE_PLAN,
    ) -> None:
        self.candidate = candidate
        self.program = program
        self.payload = payload
        self.failure_reason = failure_reason
        self.plan = plan

    @property
    def p_value(self) -> float:
        """The raw p-value entering the BH family, or the conservative default."""
        return _FAILED_P_VALUE if self.payload is None else float(self.payload["p_value"])


def _incomplete_payload_reason(payload: dict[str, Any] | None) -> str | None:
    """Why a verified payload still cannot become a complete proof object, or None.

    Guarantees: a reported effect always travels with a non-empty metric name. A number
    without its unit is not a reportable effect (AGENTS.md 3.5, 3.6), and a program that
    omits the label has not followed the contract, however genuine its stamp.
    """
    if payload is None:
        return None
    metric = payload.get("reported_effect_metric")
    if not isinstance(metric, str) or not metric.strip():
        return (
            "the program returned a reported_effect without a non-empty "
            "reported_effect_metric, so the record is incomplete; the claim is "
            "recorded as inconclusive rather than gated (AGENTS.md 3.6)"
        )
    return None


#: Starts the failure reason of a claim whose generator could not be reached at all
#: (no key, refused provider, failed request). Per-claim verdicts are unchanged by it;
#: it lets a reader of one proof object, and the batch summary, tell "the verifier never
#: ran" apart from "the claim could not be tested".
GENERATOR_UNAVAILABLE_REASON_PREFIX = "generator unavailable"


#: What a claim's template outcome is recorded as when the template run did not complete.
TEMPLATE_UNAVAILABLE = "template_unavailable"


class TemplateDisagreement(BaseModel):
    """One claim whose gate outcome differs between the LLM path and the template path.

    Diagnostic only (docs/DECISIONS_LLM_ROLES.md W8): the LLM-path outcome is the one in
    the proof object; this records that the reference test would have said otherwise.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    insight_id: str
    claim_type: str
    llm_outcome: str
    template_outcome: str


class BatchSummary(BaseModel):
    """Run-level facts a list of proof objects cannot carry on its own.

    A batch in which the generator was unreachable returns the same verdicts as a batch
    of untestable claims: REJECT / NOT_TESTABLE for every one. Only this summary says the
    difference, so a caller that reports "no insights" can check `generator_unavailable`
    first and report an error instead.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    bh_family_id: str
    generator: str = Field(description="Which generator the config selected for the run.")
    n_candidates: int = Field(ge=0)
    n_screened_out: int = Field(ge=0, description="Refused or ungenerated: not in the family.")
    n_tested: int = Field(ge=0, description="Claims whose code reached the executor.")
    generator_unavailable_count: int = Field(ge=0)
    column_check_by_claim_type: dict[str, dict[str, int]]
    n_template_comparisons: int = Field(
        default=0, ge=0, description="Claims whose template outcome was obtained (W8)."
    )
    n_template_unavailable: int = Field(
        default=0, ge=0, description="Claims whose template run did not complete (W8)."
    )
    template_unavailable_ids: list[str] = Field(default_factory=list)
    template_disagreements: list[TemplateDisagreement] = Field(default_factory=list)
    structure: DataStructure | None = Field(
        default=None, description="How the gate was told the rows depend on each other."
    )
    split: SplitRecord | None = Field(
        default=None, description="Which rows the family was tested on (PLAN D5)."
    )

    @property
    def generator_unavailable(self) -> bool:
        """True when at least one claim could not be tested because no generator ran."""
        return self.generator_unavailable_count > 0


class _ColumnCheckTally:
    """How often the column check refuses LLM-written programs, per claim type.

    The check errs toward refusing, so its cost is NOT_TESTABLE-shaped claims the LLM
    path could not test. That cost has to be measured, not guessed, before the check is
    ever loosened, and the template path is excluded because its programs are the
    reference and are not expected to be refused. Counts are logged, never gated on.
    """

    def __init__(self) -> None:
        self._programs: dict[str, int] = {}
        self._refused: dict[str, int] = {}
        self.unavailable = 0

    def record(
        self, candidate: CandidateInsight, generator: str, ok: bool, reason: str | None
    ) -> None:
        if generator != "llm":
            return
        key = candidate.claim_type.value
        self._programs[key] = self._programs.get(key, 0) + 1
        refused = not ok and (reason or "").startswith(COLUMN_POLICY_REASON_PREFIX)
        self._refused.setdefault(key, 0)
        if refused:
            self._refused[key] += 1
            _emit(
                "column_check_refused",
                candidate.insight_id,
                claim_type=key,
                reason=reason,
            )

    def summary(self) -> dict[str, dict[str, int]]:
        return {
            key: {
                "llm_programs": self._programs[key],
                "column_check_refused": self._refused.get(key, 0),
            }
            for key in sorted(self._programs)
        }


def _spec_drift(program: FalsificationProgram, payload: dict[str, Any]) -> str | None:
    """A reason when the result was produced under a different seed or resample count than
    the frozen spec, else None. Such a result is treated as a failed execution."""
    if int(payload["seed"]) != program.seed:
        return (
            f"the result used seed {payload['seed']} but the frozen plan said {program.seed}; "
            f"a result produced under a different plan is not accepted"
        )
    if int(payload["n_permutations"]) != program.n_permutations:
        return (
            f"the result used {payload['n_permutations']} resamples but the frozen plan said "
            f"{program.n_permutations}; a result produced under a different plan is not accepted"
        )
    return None


def _frozen_spec(
    program: FalsificationProgram,
    plan: TestPlan,
    split: SplitRecord | None,
    candidate: CandidateInsight,
    config: VerificationConfig,
) -> str:
    """The plan's fingerprint, from the program and what the gate assigned (S4)."""
    return spec_hash(
        code=program.source,
        seed=program.seed,
        n_permutations=declared_permutations(program.source),
        scheme=plan.scheme,
        split_digest=split.confirmation_digest if split else None,
        direction=candidate.asserted_direction.value if candidate.asserted_direction else None,
        alpha=config.statistics.alpha,
    )


def _run_one(
    candidate: CandidateInsight,
    frame: pd.DataFrame,
    config: VerificationConfig,
    generate: Generator,
    tally: _ColumnCheckTally,
    plan: TestPlan = FREE_PLAN,
    split: SplitRecord | None = None,
) -> _Tested | str:
    """Generate and execute one claim's falsification test.

    Returns a `_Tested` when code was produced -- whether or not running it worked --
    and a refusal reason string when no code could be generated at all. The two are
    different shapes of proof object, so the caller has to be able to tell them apart.
    """
    try:
        program = (
            generate(candidate, config)
            if plan == FREE_PLAN
            else generate(candidate, config, plan)
        )
        if program.scheme is not plan.scheme:
            raise GeneratorError(
                f"the generator produced a {program.scheme.value} test, but the gate "
                f"assigned {plan.scheme.value} for how these rows depend on each other"
            )
    except GeneratorUnavailable as error:
        tally.unavailable += 1
        _emit("generator_unavailable_for_claim", candidate.insight_id, error=str(error))
        return (
            f"{GENERATOR_UNAVAILABLE_REASON_PREFIX}: {error} The verifier did not run "
            f"for this claim, so it has not been tested; this says nothing about the "
            f"claim itself."
        )
    except (GeneratorError, ValueError, TypeError) as error:
        # TypeError: a generator that takes no plan was handed one; it cannot build a
        # dependence-aware test, so the claim is not tested rather than tested wrongly.
        _emit("generation_failed", candidate.insight_id, error=str(error))
        return (
            f"no falsification program could be generated for this claim: {error} "
            f"Nothing was executed, so the claim has not been tested."
        )

    frozen = _frozen_spec(program, plan, split, candidate, config)
    _emit("spec_frozen", candidate.insight_id, spec_hash=frozen)
    result = execute(program, frame, config)
    tally.record(candidate, program.generator, result.ok, result.failure_reason)
    if not result.ok:
        _emit(
            "execution_failed",
            candidate.insight_id,
            attempts=result.attempts,
            reason=result.failure_reason,
        )
        return _Tested(candidate, program, None, result.failure_reason, plan)

    incomplete = _incomplete_payload_reason(result.payload)
    if incomplete is not None:
        # The executor's required keys are the floor for "a stamped result"; the proof
        # object needs one more thing it cannot be handed without -- the unit of the
        # reported effect. Treated like any other failed execution: kept in the family
        # at p = 1.0, so it can never become SUPPORTED.
        _emit("payload_incomplete", candidate.insight_id, reason=incomplete)
        return _Tested(candidate, program, None, incomplete, plan)

    drifted = _spec_drift(program, result.payload)
    if drifted is not None:
        _emit("spec_drift", candidate.insight_id, reason=drifted)
        return _Tested(candidate, program, None, drifted, plan)

    _emit("execution_verified", candidate.insight_id, attempts=result.attempts)
    return _Tested(candidate, program, result.payload, None, plan)


def _proof_for_failed_execution(
    tested: _Tested,
    family_id: str,
    q_value: float,
    family_size: int,
    seed: int,
    split: SplitRecord | None = None,
    config: VerificationConfig | None = None,
) -> ProofObject:
    """A crash or timeout, recorded as a tested claim that concluded nothing.

    The code that failed IS the audit trail, so it is kept. The claim stays in the
    family, because it was tested and excluding it after the fact would let a failure
    quietly relax everyone else's correction.
    """
    candidate = tested.candidate
    return ProofObject(
        insight_id=candidate.insight_id,
        verdict=Verdict.REJECT,
        gate_outcome=GateOutcome.INCONCLUSIVE,
        bh_family_id=family_id,
        seed=seed,
        p_value=_FAILED_P_VALUE,
        q_value=q_value,
        effect_size=_FAILED_EFFECT_SIZE,
        effect_metric=_METRIC_BY_CLAIM_TYPE[candidate.claim_type],
        test_type=tested.program.test_type,
        falsification_code=tested.program.source,
        n_hypotheses_in_batch=family_size,
        asserted_direction=candidate.asserted_direction,
        failure_reason=tested.failure_reason,
        permutation_scheme=tested.plan.scheme,
        split=split,
        spec_hash=(
            None
            if config is None
            else _frozen_spec(tested.program, tested.plan, split, tested.candidate, config)
        ),
    )


def _proof_for_result(
    tested: _Tested,
    family_id: str,
    q_value: float,
    family_size: int,
    config: VerificationConfig,
    split: SplitRecord | None = None,
) -> ProofObject:
    """Gate one executed result and build its complete proof object.

    The q-value is the BH-corrected one, so the gate's significance check is a
    statement about the family rather than about this claim alone.
    """
    payload = tested.payload
    assert payload is not None  # _run_one returns a failure carrier otherwise
    candidate = tested.candidate
    effect_metric = EffectMetric(payload["effect_metric"])

    decision = evaluate_gate(
        q_value=q_value,
        effect_size=float(payload["effect_size"]),
        effect_metric=effect_metric,
        alpha=config.statistics.alpha,
        p_value_floor=config.p_value_floor,
        config=config.evidence,
        asserted_direction=candidate.asserted_direction,
    )
    _emit(
        "verdict_issued",
        candidate.insight_id,
        outcome=decision.outcome.value,
        verdict=decision.verdict.value,
        q_value=q_value,
        effect_size=float(payload["effect_size"]),
    )

    reported_effect = payload.get("reported_effect")
    return ProofObject(
        insight_id=candidate.insight_id,
        verdict=decision.verdict,
        gate_outcome=decision.outcome,
        bh_family_id=family_id,
        seed=int(payload["seed"]),
        p_value=float(payload["p_value"]),
        q_value=q_value,
        effect_size=float(payload["effect_size"]),
        effect_metric=effect_metric,
        test_type=tested.program.test_type,
        falsification_code=tested.program.source,
        n_hypotheses_in_batch=family_size,
        reported_effect=None if reported_effect is None else float(reported_effect),
        reported_effect_metric=payload.get("reported_effect_metric"),
        asserted_direction=candidate.asserted_direction,
        observed_direction=decision.observed_direction,
        evidence_score=decision.evidence_score,
        score_components=decision.score_components,
        permutation_scheme=tested.plan.scheme,
        split=split,
        spec_hash=_frozen_spec(tested.program, tested.plan, split, tested.candidate, config),
    )


def _claim_view(proof: ProofObject, tested: _Tested, structure: DataStructure) -> ClaimView:
    """What was tested, in the form the attacks and the interval recompute it from."""
    candidate = tested.candidate
    return ClaimView(
        claim_type=candidate.claim_type,
        var_x=candidate.variables[0],
        var_y=candidate.variables[1],
        scheme=tested.plan.scheme,
        entity_column=structure.entity_column,
        reference_group=candidate.reference_group,
        unsigned=proof.effect_metric is EffectMetric.EPSILON_SQUARED,
    )


def _with_interval(
    proof: ProofObject,
    tested: _Tested,
    frame: pd.DataFrame,
    structure: DataStructure,
    config: VerificationConfig,
) -> ProofObject:
    """`proof` with an interval on its effect; changes nothing else and never raises."""
    try:
        found = effect_interval(
            _claim_view(proof, tested, structure),
            frame,
            n_resamples=config.statistics.interval_resamples,
            confidence=config.statistics.interval_confidence,
            seed=config.statistics.seed,
        )
    except Exception as error:  # descriptive only: a missing interval changes no verdict
        _emit("interval_failed", proof.insight_id, error=f"{type(error).__name__}: {error}")
        return proof
    return proof if found is None else proof.model_copy(update={"effect_interval": found})


def _with_power(
    proof: ProofObject,
    tested: _Tested,
    frame: pd.DataFrame,
    structure: DataStructure,
    config: VerificationConfig,
) -> ProofObject:
    """`proof` with a note on the smallest effect these rows could have found.

    Guarantees: changes nothing but `power`; never raises (a note that cannot be worked
    out is simply absent); the verdict, q-value and family are untouched.
    """
    try:
        payload = tested.payload or {}
        n_observations = payload.get("n_observations")
        if n_observations is None or proof.effect_metric is None:
            return proof
        entity = structure.entity_column
        candidate = tested.candidate
        groups = (
            int(frame[candidate.variables[0]].dropna().nunique())
            if candidate.claim_type is ClaimType.GROUP_DIFFERENCE
            else None
        )
        note = power_note(
            proof.effect_metric,
            tested.plan.scheme,
            n_observations=int(n_observations),
            n_periods=(
                int(frame[PERIOD_COLUMN].nunique()) if PERIOD_COLUMN in frame else None
            ),
            n_entities=int(frame[entity].nunique()) if entity and entity in frame else None,
            groups=groups,
            alpha=config.statistics.alpha,
            power=config.statistics.power_target,
        )
    except Exception as error:  # descriptive only: a missing note changes no verdict
        _emit("power_note_failed", proof.insight_id, error=f"{type(error).__name__}: {error}")
        return proof
    return proof if note is None else proof.model_copy(update={"power": note})


def _attacked(
    proof: ProofObject,
    tested: _Tested,
    frame: pd.DataFrame,
    structure: DataStructure,
    config: VerificationConfig,
) -> ProofObject:
    """`proof` with its attacks attached, and REJECT / FRAGILE if any broke it.

    Guarantees: only a PASS enters; the result is the same PASS with attacks recorded,
    or a REJECT whose reason names the attack. Never raises: an attack run that fails
    as a whole leaves the PASS with no attacks and logs why, because attacks can only
    lower a verdict and a crash is not evidence against the claim.
    """
    candidate = tested.candidate
    claim = _claim_view(proof, tested, structure)
    hints = None
    if config.attacks.refuter_enabled:
        outcome = suggest_hints(claim, frame, config)
        hints = outcome.hints
        _emit(
            "refuter",
            proof.insight_id,
            status=outcome.status,
            controls=list(outcome.hints.controls),
            groups=list(outcome.hints.groups),
            dropped=list(outcome.dropped),
        )
    try:
        results = run_attacks(
            claim, frame, config.attacks, seed=config.statistics.seed, hints=hints
        )
    except Exception as error:  # attacks lower verdicts only; a crash changes nothing
        _emit("attacks_failed", proof.insight_id, error=f"{type(error).__name__}: {error}")
        return proof
    broken = [r for r in results if r.outcome is AttackOutcome.BROKEN]
    _emit(
        "attacks_run",
        proof.insight_id,
        survived=sum(r.outcome is AttackOutcome.SURVIVED for r in results),
        broken=[r.attack_id for r in broken],
    )
    if not broken:
        return proof.model_copy(update={"attacks": results})
    first = broken[0]
    return ProofObject.model_validate(
        {
            **proof.model_dump(),
            "verdict": Verdict.REJECT,
            "gate_outcome": GateOutcome.FRAGILE,
            "evidence_score": None,
            "score_components": None,
            "attacks": [r.model_dump() for r in results],
            "failure_reason": (
                f"passed the gate but did not survive the {first.name.lower()} attack: "
                f"{first.reason}"
            ),
        }
    )


def _shadow_template_outcomes(
    tested: Sequence[_Tested],
    frame: pd.DataFrame,
    config: VerificationConfig,
    family_id: str,
) -> dict[str, GateOutcome | None]:
    """Gate outcome the template test would give each tested claim; None if it crashed.

    DIAGNOSTIC ONLY (W8). Guarantees: touches no proof, q-value, p-value or the real BH
    family. Each tested claim's template program is run on the same frame, config and
    seed; the template p-values then go through their OWN BH correction over a family
    of the same size as the real one (a claim with no template or a failed template run
    keeps its LLM-path p-value as a placeholder, so the size and the correction stay
    comparable), and the same gate decides each outcome. The result is discarded after
    the comparison. Never raises: any failure of a template run becomes None.
    """
    template_results: dict[str, dict[str, Any] | None] = {}
    for item in tested:
        candidate = item.candidate
        if (
            item.program.generator == "template"
            or candidate.claim_type not in templates.SUPPORTED_CLAIM_TYPES
        ):
            continue
        try:
            result = execute(
                generate_from_template(candidate, config, item.plan), frame, config
            )
            payload = result.payload if result.ok else None
            if payload is not None and _incomplete_payload_reason(payload) is not None:
                payload = None
            if payload is not None:
                EffectMetric(payload["effect_metric"])
                float(payload["p_value"])
                float(payload["effect_size"])
        except Exception as error:  # diagnostic: must never take the batch down
            _log.warning(
                json.dumps(
                    {
                        "event": "template_unavailable",
                        "insight_id": candidate.insight_id,
                        "bh_family_id": family_id,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
            )
            payload = None
        else:
            if payload is None:
                _log.warning(
                    json.dumps(
                        {
                            "event": "template_unavailable",
                            "insight_id": candidate.insight_id,
                            "bh_family_id": family_id,
                            "error": result.failure_reason or "no verified result",
                        }
                    )
                )
        template_results[candidate.insight_id] = payload

    if not template_results:
        return {}

    shadow_p = [
        float(template_results[item.candidate.insight_id]["p_value"])  # type: ignore[index]
        if template_results.get(item.candidate.insight_id) is not None
        else item.p_value
        for item in tested
    ]
    shadow_q = apply_bh(shadow_p, config.statistics.alpha)
    outcomes: dict[str, GateOutcome | None] = {}
    for item, q_value in zip(tested, shadow_q, strict=True):
        insight_id = item.candidate.insight_id
        if insight_id not in template_results:
            continue
        payload = template_results[insight_id]
        if payload is None:
            outcomes[insight_id] = None
            continue
        decision = evaluate_gate(
            q_value=q_value,
            effect_size=float(payload["effect_size"]),
            effect_metric=EffectMetric(payload["effect_metric"]),
            alpha=config.statistics.alpha,
            p_value_floor=config.p_value_floor,
            config=config.evidence,
            asserted_direction=item.candidate.asserted_direction,
        )
        outcomes[insight_id] = decision.outcome
    return outcomes


def verify_batch(
    candidates: Sequence[CandidateInsight],
    frame: pd.DataFrame,
    config: VerificationConfig,
    *,
    generate: Generator | None = None,
    structure: DataStructure | None = None,
    split: SplitRecord | None = None,
) -> list[ProofObject]:
    """Verify a batch and return one proof object per candidate.

    The proofs-only entry point existing callers use. Callers that must tell "the
    generator was unreachable" from "the claims were untestable" call
    `verify_batch_with_summary` instead; the per-claim result is identical.
    """
    return verify_batch_with_summary(
        candidates, frame, config, generate=generate, structure=structure, split=split
    )[0]


def verify_batch_with_summary(
    candidates: Sequence[CandidateInsight],
    frame: pd.DataFrame,
    config: VerificationConfig,
    *,
    generate: Generator | None = None,
    structure: DataStructure | None = None,
    split: SplitRecord | None = None,
) -> tuple[list[ProofObject], BatchSummary]:
    """Verify a whole batch of candidate insights: one proof object each, plus a summary.

    Guarantees:

    * **One proof per candidate, in input order.** Callers zip the two lists together;
      a reordering would attach every verdict to the wrong claim, and a dropped
      candidate would look like a claim nobody made.
    * **BH runs exactly once**, over the claims that were actually tested, after every
      p-value is in (AGENTS.md 3.2). Screened-out claims are excluded from the family
      and from `n_hypotheses_in_batch`.
    * **No path to PASS except a SUPPORTED gate decision.** A refused claim, a failed
      generation, a crash, a timeout and a malformed result all end in REJECT.
    * **Reproducible.** With the same frame, the same config and the same batch, every
      p-value, q-value and verdict is identical (AGENTS.md 3.4).

    `generate` overrides the configured generator, for the ablation harness that needs
    to hold everything else fixed while swapping the code-generation path. It defaults
    to whatever `configs/verification.yaml` selects.

    * **The null matches the rows (PLAN D6).** `structure` says how the rows depend on
      each other; each claim is assigned a permutation scheme from it, or refused as
      NOT_TESTABLE when no valid null exists. With no `structure` the caller is taken to
      declare independent rows, and every proof records that as `free`.
    * **Tested on the rows given.** `frame` is the confirmation rows when the run was
      split (PLAN D5); `split` is recorded on every proof so that can be checked.

    Raises `ValueError` for a batch containing a repeated `insight_id`, which would
    silently collapse two verdicts into one, and for a batch larger than
    `statistics.m_max`, which the resample count was not sized for.
    """
    _require_unique_ids(candidates)
    if len(candidates) > config.statistics.m_max:
        raise ValueError(
            f"{len(candidates)} claims exceed statistics.m_max = {config.statistics.m_max}; "
            f"the resample count is sized for families up to that size"
        )
    structure = structure or DataStructure.independent_rows()
    frame = with_period_column(frame, structure)
    if not candidates:
        return [], BatchSummary(
            bh_family_id=_family_id(candidates),
            generator=config.llm.generator,
            n_candidates=0,
            n_screened_out=0,
            n_tested=0,
            generator_unavailable_count=0,
            column_check_by_claim_type={},
            structure=structure,
            split=split,
        )

    family_id = _family_id(candidates)
    seed = config.statistics.seed
    generator = generate or get_generator(config)
    columns = list(frame.columns)
    tally = _ColumnCheckTally()

    # --- screen, generate, execute ------------------------------------------
    # Nothing is corrected or gated yet: BH needs every p-value in hand first.
    outcomes: list[ProofObject | _Tested] = []
    for candidate in candidates:
        admissibility = screen(candidate, columns)
        if not admissibility.admissible:
            reason = admissibility.reason or "the claim was refused by the admissibility screen"
            _emit("screened_out", candidate.insight_id, reason=reason)
            outcomes.append(_not_testable(candidate, family_id, seed, reason, split))
            continue

        plan = assign_plan(candidate, frame, structure, config)
        if isinstance(plan, str):
            _emit("screened_out", candidate.insight_id, reason=plan)
            outcomes.append(_not_testable(candidate, family_id, seed, plan, split))
            continue

        outcome = _run_one(candidate, frame, config, generator, tally, plan, split)
        if isinstance(outcome, str):
            outcomes.append(_not_testable(candidate, family_id, seed, outcome, split))
        else:
            outcomes.append(outcome)

    _log.info(
        json.dumps(
            {
                "event": "column_check_summary",
                "bh_family_id": family_id,
                "by_claim_type": tally.summary(),
            }
        )
    )

    # --- correct once, across the whole family -------------------------------
    tested = [item for item in outcomes if isinstance(item, _Tested)]
    family_size = len(tested)
    raw_p_values = [item.p_value for item in tested]
    q_values = apply_bh(raw_p_values, config.statistics.alpha) if tested else []
    _log.info(
        json.dumps(
            {
                "event": "bh_applied",
                "bh_family_id": family_id,
                "n_hypotheses_in_batch": family_size,
                "n_screened_out": len(candidates) - family_size,
                "alpha": config.statistics.alpha,
            }
        )
    )

    # --- gate, in the order the candidates arrived ---------------------------
    # `tested` was built by walking `outcomes` in order and `apply_bh` preserves input
    # order, so stepping the q-values in step with the tested claims pairs each claim
    # with its own correction.
    corrected = iter(q_values)
    proofs: list[ProofObject] = []
    for item in outcomes:
        if isinstance(item, ProofObject):
            proofs.append(item)
            continue
        q_value = next(corrected)
        if item.payload is None:
            proofs.append(
                _proof_for_failed_execution(
                    item, family_id, q_value, family_size, seed, split, config
                )
            )
        else:
            proofs.append(
                _proof_for_result(item, family_id, q_value, family_size, config, split)
            )

    by_id = {item.candidate.insight_id: item for item in tested}
    # --- power note: descriptive, on claims that were tested and not significant ----
    proofs = [
        _with_power(proof, by_id[proof.insight_id], frame, structure, config)
        if proof.gate_outcome is GateOutcome.INCONCLUSIVE
        and proof.failure_reason is None
        and proof.insight_id in by_id
        else proof
        for proof in proofs
    ]

    # --- interval on the effect: descriptive, on claims that passed the gate -------
    proofs = [
        _with_interval(proof, by_id[proof.insight_id], frame, structure, config)
        if proof.verdict is Verdict.PASS and proof.insight_id in by_id
        else proof
        for proof in proofs
    ]

    # --- falsification attacks (PLAN §7): a one-way ratchet on every PASS -----
    proofs = [
        _attacked(proof, by_id[proof.insight_id], frame, structure, config)
        if proof.verdict is Verdict.PASS
        else proof
        for proof in proofs
    ]

    # --- agreement check (W8): diagnostic, after every verdict is final ------
    # Runs only on the LLM path. Reads the proofs, never writes them.
    disagreements: list[TemplateDisagreement] = []
    unavailable_ids: list[str] = []
    n_compared = 0
    if config.llm.generator == "llm" and tested:
        try:
            shadow = _shadow_template_outcomes(tested, frame, config, family_id)
        except Exception as error:  # diagnostic only: never fail the batch over it
            _log.warning(
                json.dumps(
                    {
                        "event": "template_comparison_failed",
                        "bh_family_id": family_id,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
            )
            shadow = {}
        proof_by_id = {proof.insight_id: proof for proof in proofs}
        for item in tested:
            insight_id = item.candidate.insight_id
            if insight_id not in shadow:
                continue
            template_outcome = shadow[insight_id]
            if template_outcome is None:
                unavailable_ids.append(insight_id)
                continue
            n_compared += 1
            llm_outcome = proof_by_id[insight_id].gate_outcome
            if template_outcome is not llm_outcome:
                flagged = TemplateDisagreement(
                    insight_id=insight_id,
                    claim_type=item.candidate.claim_type.value,
                    llm_outcome=llm_outcome.value,
                    template_outcome=template_outcome.value,
                )
                disagreements.append(flagged)
                _log.warning(
                    json.dumps(
                        {
                            "event": "template_disagreement",
                            "bh_family_id": family_id,
                            **flagged.model_dump(),
                            "message": (
                                "the template reference test reaches a different gate "
                                "outcome than the LLM-written program; the LLM-path "
                                "verdict stands and this is flagged for review only."
                            ),
                        }
                    )
                )

    summary = BatchSummary(
        bh_family_id=family_id,
        generator=config.llm.generator,
        n_candidates=len(candidates),
        n_screened_out=len(candidates) - family_size,
        n_tested=family_size,
        generator_unavailable_count=tally.unavailable,
        column_check_by_claim_type=tally.summary(),
        n_template_comparisons=n_compared,
        n_template_unavailable=len(unavailable_ids),
        template_unavailable_ids=unavailable_ids,
        template_disagreements=disagreements,
        structure=structure,
        split=split,
    )
    if summary.generator_unavailable:
        _log.warning(
            json.dumps(
                {
                    "event": "generator_unavailable",
                    "bh_family_id": family_id,
                    "generator": summary.generator,
                    "generator_unavailable_count": summary.generator_unavailable_count,
                    "n_candidates": summary.n_candidates,
                    "message": (
                        "the falsification generator could not be reached for some or all "
                        "claims; those claims were NOT tested. Zero insights from this run "
                        "means the verifier did not run, not that nothing was found."
                    ),
                }
            )
        )
    return proofs, summary
