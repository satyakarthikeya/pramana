"""Generate in the trusted process; execute through the isolated gateway worker."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pramana.contracts import CandidateInsight, DataStructure, ProofObject, SplitRecord
from pramana.contracts.enums import PermutationScheme
from pramana.verification.admissibility import screen
from pramana.verification.config import VerificationConfig
from pramana.verification.falsification.generator import (
    FalsificationProgram,
    GeneratorError,
    GeneratorUnavailable,
    get_generator,
)
from pramana.verification.gateway import BatchSummary
from pramana.verification.schemes import (
    FREE_PLAN,
    TestPlan,
    assign_plan,
    confirmation_frame,
    with_period_column,
)


def gate_rows(
    frame: pd.DataFrame, structure: DataStructure | None, config: VerificationConfig
) -> tuple[pd.DataFrame, SplitRecord | None]:
    """The rows the gate tests on: the confirmation split, or `frame` with no structure.

    Guarantees: with a structure, never a row the proposer explored (PLAN D5).
    """
    if structure is None:
        return frame, None
    return confirmation_frame(frame, structure, config)


def validate_summary(
    value: Any, candidates: Sequence[CandidateInsight], proofs: Sequence[ProofObject]
) -> BatchSummary:
    """Accept gateway diagnostics only when bound to this complete family."""
    summary = value if isinstance(value, BatchSummary) else BatchSummary.model_validate(value)
    if (
        summary.n_candidates != len(candidates)
        or summary.n_tested + summary.n_screened_out != len(candidates)
        or summary.generator_unavailable_count > summary.n_screened_out
        or any(proof.bh_family_id != summary.bh_family_id for proof in proofs)
    ):
        raise ValueError("Verification summary does not match the candidate/proof family")
    candidate_ids = {candidate.insight_id for candidate in candidates}
    diagnostic_ids = set(summary.template_unavailable_ids) | {
        item.insight_id for item in summary.template_disagreements
    }
    if not diagnostic_ids <= candidate_ids:
        raise ValueError("Verification diagnostics reference another candidate family")
    return summary


class PreparedProgram(BaseModel):
    """Record either the exact checked source or an explicit generation failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_json: str
    program: FalsificationProgram | None = None
    failure_reason: str | None = Field(default=None, min_length=1)
    generator_unavailable: bool = False

    @model_validator(mode="after")
    def one_outcome(self) -> PreparedProgram:
        if (self.program is None) == (self.failure_reason is None):
            raise ValueError("prepared generation needs exactly one outcome")
        if self.program is not None and self.generator_unavailable:
            raise ValueError("a generated program cannot mark its generator unavailable")
        return self


class PreparedBatch(BaseModel):
    """Bind generated code to the complete candidate batch and verification config."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    config_digest: str
    programs: list[PreparedProgram]


def _config_digest(config: VerificationConfig) -> str:
    return hashlib.sha256(config.model_dump_json().encode()).hexdigest()


def prepare_verification(
    candidates: Sequence[CandidateInsight],
    frame: pd.DataFrame,
    config: VerificationConfig,
    structure: DataStructure | None = None,
) -> PreparedBatch:
    """Use the verification owner's screen/generator without executing any code.

    `frame` is the rows the gate will test on (see `gate_rows`), so each claim's code is
    generated for the same null the worker's gateway assigns.
    """
    generate = get_generator(config)
    planned = structure or DataStructure.independent_rows()
    rows = with_period_column(frame, planned)
    programs = []
    for candidate in candidates:
        admission = screen(candidate, list(frame.columns))
        try:
            if not admission.admissible:
                raise GeneratorError(admission.reason or "Claim is not testable")
            plan = assign_plan(candidate, rows, planned, config)
            if isinstance(plan, str):
                raise GeneratorError(plan)
            program = (
                generate(candidate, config)
                if plan.scheme is PermutationScheme.FREE
                else generate(candidate, config, plan)
            )
            programs.append(
                PreparedProgram(candidate_json=candidate.model_dump_json(), program=program)
            )
        except (GeneratorError, ValueError) as error:
            programs.append(
                PreparedProgram(
                    candidate_json=candidate.model_dump_json(),
                    failure_reason=str(error),
                    generator_unavailable=isinstance(error, GeneratorUnavailable),
                )
            )
    return PreparedBatch(config_digest=_config_digest(config), programs=programs)


def prepared_generator(
    batch: PreparedBatch,
    candidates: Sequence[CandidateInsight],
    config: VerificationConfig,
) -> Callable[[CandidateInsight, VerificationConfig], FalsificationProgram]:
    """Supply previously checked code; worker generation never calls an external API."""
    if batch.config_digest != _config_digest(config):
        raise ValueError("Trusted and worker verification configurations differ")
    if [item.candidate_json for item in batch.programs] != [
        candidate.model_dump_json() for candidate in candidates
    ]:
        raise ValueError("Prepared programs do not match the exact candidate family")
    by_id = dict(zip((c.insight_id for c in candidates), batch.programs, strict=True))
    if len(by_id) != len(candidates):
        raise ValueError("Prepared candidate IDs must be unique")

    def generate(
        candidate: CandidateInsight, current: VerificationConfig, plan: TestPlan = FREE_PLAN
    ) -> FalsificationProgram:
        if _config_digest(current) != batch.config_digest:
            raise GeneratorError("Verification configuration changed after generation")
        prepared = by_id[candidate.insight_id]
        if prepared.program is None:
            if prepared.generator_unavailable:
                raise GeneratorUnavailable(prepared.failure_reason or "Generator unavailable")
            raise GeneratorError(prepared.failure_reason or "Generation failed")
        program = prepared.program
        if (
            program.insight_id != candidate.insight_id
            or program.claim_type != candidate.claim_type
            or [program.var_x, program.var_y] != candidate.variables
            or program.seed != current.statistics.seed
            or program.n_permutations != current.statistics.n_permutations
            or program.generator != current.llm.generator
            or program.scheme is not plan.scheme
            or program.structure_columns != plan.columns
        ):
            raise GeneratorError("Prepared program metadata does not match the candidate/config")
        return program

    return generate
