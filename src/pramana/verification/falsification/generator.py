"""The generator interface: a candidate insight in, an executable program out.

This module is deliberately thin. `templates.py` already does the real work -- the
deterministic, per-`ClaimType` rendering that produces the code the executor runs --
and this file only adapts it to the shape the rest of the gateway consumes:

    CandidateInsight + VerificationConfig  ->  FalsificationProgram

`FalsificationProgram` is the unit the executor and the gateway pass around. It carries
the rendered source together with the metadata needed to interpret the result, so a
proof object can record WHAT ran, with WHICH seed and how many resamples, WITHOUT
re-deriving any of it from the candidate afterwards. `generator` names which path
produced the code, so an ablation can tell a template run from an LLM run in the
audit trail rather than by inference.

Scope note: the LLM (DeepSeek V4) generator and `get_generator`'s config-driven
selection are NOT here yet -- that is SCOPE.md 4 step 6. This file currently contains
only the deterministic path, which is the DEFAULT and needs no API key and no network.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 6 (deterministic path only)
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType, TestType
from pramana.verification.config import VerificationConfig
from pramana.verification.falsification import templates

#: Every supported claim type is a relationship between exactly two columns, and the
#: templates render `VAR_X` / `VAR_Y` from them in that order.
_REQUIRED_VARIABLES = 2


class FalsificationProgram(BaseModel):
    """One rendered falsification test, ready to execute.

    Guarantees: frozen, so the source that was policy-checked is the source that runs
    and the source recorded in the proof object. `source` is the complete module --
    the executor writes it to disk unmodified, adding nothing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    insight_id: str = Field(min_length=1)
    claim_type: ClaimType
    var_x: str = Field(min_length=1)
    var_y: str = Field(min_length=1)
    test_type: TestType = Field(description="Which vetted procedure the code calls.")
    n_permutations: int = Field(ge=1, description="Resamples the rendered code will run.")
    seed: int = Field(description="Baked into the source, so the run is reproducible.")
    source: str = Field(min_length=1, description="The complete generated module.")
    generator: str = Field(
        min_length=1,
        description="Which path produced this code ('template', 'llm'). Recorded so an "
        "ablation can distinguish them in the audit trail rather than by inference.",
    )


def generate_from_template(
    candidate: CandidateInsight, config: VerificationConfig
) -> FalsificationProgram:
    """Render `candidate` into an executable falsification program, with no LLM.

    Guarantees: byte-identical output for the same `(candidate, config)`, so the
    `falsification_code` stored in a proof object is a reproducible record of exactly
    what ran (AGENTS.md 4.4). Every tunable in the rendered source -- resample count,
    seed, minimum observations -- comes from `configs/verification.yaml`, never from a
    literal here or in the template.

    Raises for a claim that does not name exactly two columns, and (via
    `templates.render`) for a claim type with no template: the gateway fails closed
    rather than substituting a generic test. In practice the admissibility screen has
    already refused both, so this is the second of two locks.
    """
    if len(candidate.variables) != _REQUIRED_VARIABLES:
        raise ValueError(
            f"{candidate.insight_id}: a falsification template needs exactly "
            f"{_REQUIRED_VARIABLES} variables; got {candidate.variables}"
        )

    var_x, var_y = candidate.variables
    source = templates.render(
        insight_id=candidate.insight_id,
        claim=candidate.claim,
        claim_type=candidate.claim_type,
        var_x=var_x,
        var_y=var_y,
        n_permutations=config.statistics.n_permutations,
        seed=config.statistics.seed,
        min_observations=config.statistics.min_observations,
        reference_group=candidate.reference_group,
    )
    return FalsificationProgram(
        insight_id=candidate.insight_id,
        claim_type=candidate.claim_type,
        var_x=var_x,
        var_y=var_y,
        test_type=TestType.PERMUTATION,
        n_permutations=config.statistics.n_permutations,
        seed=config.statistics.seed,
        source=source,
        generator="template",
    )
