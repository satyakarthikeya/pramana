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

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType, EffectMetric, GateOutcome, Verdict
from pramana.contracts.proof_object import ProofObject
from pramana.verification.admissibility import screen
from pramana.verification.config import VerificationConfig
from pramana.verification.evidence import evaluate_gate
from pramana.verification.executor.runner import execute
from pramana.verification.falsification.generator import (
    FalsificationProgram,
    GeneratorError,
    get_generator,
)
from pramana.verification.fdr import apply_bh

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
}

#: Prefix on every family identifier, so the string is self-describing in a log line.
_FAMILY_PREFIX = "bh"

#: Enough hash to be unique across a project's runs, short enough to read.
_FAMILY_DIGEST_LENGTH = 12

Generator = Callable[[CandidateInsight, VerificationConfig], FalsificationProgram]


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
    candidate: CandidateInsight, family_id: str, seed: int, reason: str
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
    )


class _Tested:
    """One claim that reached the executor, holding what the gate will need.

    A small mutable carrier rather than a model: it exists only between execution and
    correction, never leaves this module, and never becomes output.
    """

    __slots__ = ("candidate", "program", "payload", "failure_reason")

    def __init__(
        self,
        candidate: CandidateInsight,
        program: FalsificationProgram,
        payload: dict[str, Any] | None,
        failure_reason: str | None,
    ) -> None:
        self.candidate = candidate
        self.program = program
        self.payload = payload
        self.failure_reason = failure_reason

    @property
    def p_value(self) -> float:
        """The raw p-value entering the BH family, or the conservative default."""
        return _FAILED_P_VALUE if self.payload is None else float(self.payload["p_value"])


def _run_one(
    candidate: CandidateInsight,
    frame: pd.DataFrame,
    config: VerificationConfig,
    generate: Generator,
) -> _Tested | str:
    """Generate and execute one claim's falsification test.

    Returns a `_Tested` when code was produced -- whether or not running it worked --
    and a refusal reason string when no code could be generated at all. The two are
    different shapes of proof object, so the caller has to be able to tell them apart.
    """
    try:
        program = generate(candidate, config)
    except (GeneratorError, ValueError) as error:
        _emit("generation_failed", candidate.insight_id, error=str(error))
        return (
            f"no falsification program could be generated for this claim: {error} "
            f"Nothing was executed, so the claim has not been tested."
        )

    result = execute(program, frame, config)
    if not result.ok:
        _emit(
            "execution_failed",
            candidate.insight_id,
            attempts=result.attempts,
            reason=result.failure_reason,
        )
        return _Tested(candidate, program, None, result.failure_reason)

    _emit("execution_verified", candidate.insight_id, attempts=result.attempts)
    return _Tested(candidate, program, result.payload, None)


def _proof_for_failed_execution(
    tested: _Tested, family_id: str, q_value: float, family_size: int, seed: int
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
    )


def _proof_for_result(
    tested: _Tested, family_id: str, q_value: float, family_size: int, config: VerificationConfig
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
    )


def verify_batch(
    candidates: Sequence[CandidateInsight],
    frame: pd.DataFrame,
    config: VerificationConfig,
    *,
    generate: Generator | None = None,
) -> list[ProofObject]:
    """Verify a whole batch of candidate insights and return one proof object each.

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

    Raises `ValueError` for a batch containing a repeated `insight_id`, which would
    silently collapse two verdicts into one.
    """
    _require_unique_ids(candidates)
    if not candidates:
        return []

    family_id = _family_id(candidates)
    seed = config.statistics.seed
    generator = generate or get_generator(config)
    columns = list(frame.columns)

    # --- screen, generate, execute ------------------------------------------
    # Nothing is corrected or gated yet: BH needs every p-value in hand first.
    outcomes: list[ProofObject | _Tested] = []
    for candidate in candidates:
        admissibility = screen(candidate, columns)
        if not admissibility.admissible:
            reason = admissibility.reason or "the claim was refused by the admissibility screen"
            _emit("screened_out", candidate.insight_id, reason=reason)
            outcomes.append(_not_testable(candidate, family_id, seed, reason))
            continue

        outcome = _run_one(candidate, frame, config, generator)
        if isinstance(outcome, str):
            outcomes.append(_not_testable(candidate, family_id, seed, outcome))
        else:
            outcomes.append(outcome)

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
                _proof_for_failed_execution(item, family_id, q_value, family_size, seed)
            )
        else:
            proofs.append(_proof_for_result(item, family_id, q_value, family_size, config))
    return proofs
