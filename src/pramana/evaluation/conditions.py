"""The four ablation conditions as FLAGS on ONE pipeline (SPEC.md 4).

    A  analysis loop off, no gate     single LLM call; everything it proposes is reported
    B  analysis loop on,  no gate     NOT BUILT -- stub
    C  analysis loop on,  judgement   NOT BUILT -- stub; the strongest baseline (issue 3)
    D  analysis loop on,  execution   the full gateway, `verify_batch_with_summary`

One pipeline, four settings: the conditions must differ only in the variable under
study. A and D share the proposal step, the candidate contract and the scoring; D alone
adds the gate.

The LLM seam
------------
The analysis agent may not exist yet, and the harness must not import another member's
module to reach a model. The proposal step is therefore an injected `Proposer`: a
callable from the frame to `CandidateInsight`s, plus the name of the model it runs.
Tests inject a deterministic double. A run configured for a model either gets that
model's output or FAILS CLOSED (AGENTS.md 2): a proposer reporting a different model,
or raising, is a `ConditionRunError`, never an empty reported set and never a quiet swap.

Owner: P.P. Satya Karthikeya
Scope: src/pramana/evaluation/SPEC.md 4
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import Verdict
from pramana.contracts.proof_object import ProofObject
from pramana.evaluation.config import EvaluationConfig
from pramana.verification.config import VerificationConfig
from pramana.verification.gateway import BatchSummary, Generator, verify_batch_with_summary


class Condition(StrEnum):
    """The four systems compared in the ablation (PROJECT.md 6)."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


class ConditionFlags(BaseModel):
    """What one condition switches on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_loop: bool
    gate: Literal["none", "judgement", "execution"]


CONDITION_FLAGS: dict[Condition, ConditionFlags] = {
    Condition.A: ConditionFlags(analysis_loop=False, gate="none"),
    Condition.B: ConditionFlags(analysis_loop=True, gate="none"),
    Condition.C: ConditionFlags(analysis_loop=True, gate="judgement"),
    Condition.D: ConditionFlags(analysis_loop=True, gate="execution"),
}


class ConditionRunError(RuntimeError):
    """A run could not be completed honestly. It is an error, never zero insights."""


@dataclass(frozen=True)
class Proposer:
    """The injected LLM seam: a named model and the call that proposes claims.

    `propose` receives the frame and returns structured `CandidateInsight`s (the model
    never authors verdicts or statistics; AGENTS.md 2). `model` is what the call runs.
    """

    model: str
    propose: Callable[[pd.DataFrame], Sequence[CandidateInsight]]


@dataclass(frozen=True)
class ProposerSet:
    """One proposer per setting of the `analysis_loop` flag."""

    single_call: Proposer
    analysis_loop: Proposer | None = None

    def for_flags(self, flags: ConditionFlags) -> Proposer:
        chosen = self.analysis_loop if flags.analysis_loop else self.single_call
        if chosen is None:
            raise ConditionRunError("no proposer was supplied for the analysis-loop setting")
        return chosen


class ConditionResult(BaseModel):
    """What one condition produced for one dataset."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    condition: Condition
    model: str
    generator: str | None
    candidates: list[CandidateInsight]
    reported_ids: list[str]
    proofs: list[ProofObject] | None
    bh_family_id: str | None
    summary: BatchSummary | None


def _stub(condition: Condition, what: str) -> NotImplementedError:
    return NotImplementedError(
        f"condition {condition.value} ({what}) is not built. It needs the agent loop and, "
        f"for C, a fairly built LLM judge: see src/pramana/evaluation/SPEC.md 4 and "
        f"docs/OPEN_ISSUES.md issue 3 (C must be built seriously, same model and context, "
        f"a prompt written to make it succeed)."
    )


def _propose(
    proposer: Proposer, frame: pd.DataFrame, expected_model: str
) -> list[CandidateInsight]:
    """Call the proposer, failing closed on a model mismatch, an error or a repeated id."""
    if proposer.model != expected_model:
        raise ConditionRunError(
            f"the run is configured for model {expected_model!r} but the proposer runs "
            f"{proposer.model!r}; refusing to substitute a model silently (AGENTS.md 2)"
        )
    try:
        candidates = list(proposer.propose(frame))
    except Exception as error:
        raise ConditionRunError(
            f"the proposer for model {proposer.model!r} failed: {error}. The condition did "
            f"not run; this is not a result of zero insights."
        ) from error
    ids = [c.insight_id for c in candidates]
    if len(ids) != len(set(ids)):
        raise ConditionRunError("the proposer returned a repeated insight_id")
    return candidates


def run_condition(
    condition: Condition,
    frame: pd.DataFrame,
    *,
    dataset_id: str,
    proposers: ProposerSet,
    verification: VerificationConfig,
    evaluation: EvaluationConfig,
    generate: Generator | None = None,
) -> ConditionResult:
    """Run one condition on one dataset and return what it REPORTED.

    Guarantees: B and C raise `NotImplementedError` before anything runs; A reports every
    proposal; D reports exactly the claims whose verdict is PASS, with every proof object
    kept; a missing or unreachable model or generator raises `ConditionRunError`.
    `dataset_id` labels the run; `generate` overrides the gateway's generator for tests.
    """
    if condition is Condition.B:
        raise _stub(condition, "agent loop, no gate")
    if condition is Condition.C:
        raise _stub(condition, "agent loop + LLM judgement")

    flags = CONDITION_FLAGS[condition]
    proposer = proposers.for_flags(flags)
    candidates = _propose(proposer, frame, evaluation.conditions.analysis_model)

    if flags.gate == "none":
        return ConditionResult(
            condition=condition,
            model=proposer.model,
            generator=None,
            candidates=candidates,
            reported_ids=[c.insight_id for c in candidates],
            proofs=None,
            bh_family_id=None,
            summary=None,
        )

    proofs, summary = verify_batch_with_summary(candidates, frame, verification, generate=generate)
    if summary.generator_unavailable:
        raise ConditionRunError(
            f"dataset {dataset_id!r}: the falsification generator "
            f"{summary.generator!r} was unreachable for "
            f"{summary.generator_unavailable_count} claim(s); the verifier did not run, "
            f"so this is an error and not zero insights"
        )
    passed = {p.insight_id for p in proofs if p.verdict is Verdict.PASS}
    return ConditionResult(
        condition=condition,
        model=proposer.model,
        generator=summary.generator,
        candidates=candidates,
        reported_ids=[c.insight_id for c in candidates if c.insight_id in passed],
        proofs=proofs,
        bh_family_id=summary.bh_family_id,
        summary=summary,
    )
