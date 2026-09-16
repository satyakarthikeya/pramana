"""Hand-written `CandidateInsight` batches, standing in for the analysis module.

These are what P. Rohith's generator will eventually emit. Writing them by hand now
means the gateway can be built, tested and demonstrated end to end without waiting on
another member's module -- and when the real generator arrives, these stay as the
regression cases.

Claim wording follows the hedged templates the analysis module is asked to use
("is associated with", "tends to be higher in"), so the admissible fixtures pass the
screen for the right reason rather than by accident.
"""

from __future__ import annotations

from typing import Any, Final

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType, Direction


def candidate(
    insight_id: str,
    claim: str,
    claim_type: ClaimType,
    variables: list[str],
    *,
    direction: Direction | None = None,
    evidence: dict[str, Any] | None = None,
    reference_group: str | None = None,
    dataset_ref: str = "toy_frame",
) -> CandidateInsight:
    """Build a candidate with the fixture defaults filled in."""
    return CandidateInsight(
        insight_id=insight_id,
        claim=claim,
        claim_type=claim_type,
        variables=variables,
        dataset_ref=dataset_ref,
        analysis_evidence=evidence or {},
        asserted_direction=direction,
        reference_group=reference_group,
    )


# --- claims the gateway can and should test -------------------------------

TRUE_CORRELATION: Final = candidate(
    "c-true-correlation",
    "bmi is associated with age",
    ClaimType.CORRELATION,
    ["age", "bmi"],
    direction=Direction.POSITIVE,
    evidence={"stat": "spearman_rho", "raw_value": 0.45},
)

FALSE_CORRELATION: Final = candidate(
    "c-false-correlation",
    "decoy is associated with age",
    ClaimType.CORRELATION,
    ["age", "decoy"],
    direction=Direction.POSITIVE,
    evidence={"stat": "spearman_rho", "raw_value": 0.09},
)

NULL_CORRELATION: Final = candidate(
    "c-null-correlation",
    "noise_b is associated with noise_a",
    ClaimType.CORRELATION,
    ["noise_a", "noise_b"],
    direction=Direction.POSITIVE,
)

WRONG_DIRECTION: Final = candidate(
    "c-wrong-direction",
    "bmi tends to be lower when age is higher",
    ClaimType.CORRELATION,
    ["age", "bmi"],
    direction=Direction.NEGATIVE,
    evidence={"stat": "spearman_rho", "raw_value": -0.45},
)

TRUE_GROUP_DIFFERENCE: Final = candidate(
    "c-true-group",
    "income tends to be higher in urban areas",
    ClaimType.GROUP_DIFFERENCE,
    ["area", "income"],
    direction=Direction.POSITIVE,
    reference_group="urban",
)

NULL_GROUP_DIFFERENCE: Final = candidate(
    "c-null-group",
    "noise_a tends to differ between regions",
    ClaimType.GROUP_DIFFERENCE,
    ["region", "noise_a"],
)

TRUE_TREND: Final = candidate(
    "c-true-trend",
    "visits is associated with month",
    ClaimType.TREND,
    ["month", "visits"],
    direction=Direction.POSITIVE,
)

NULL_TREND: Final = candidate(
    "c-null-trend",
    "noise_a is associated with month",
    ClaimType.TREND,
    ["month", "noise_a"],
    direction=Direction.POSITIVE,
)

TESTABLE_CANDIDATES: Final[list[CandidateInsight]] = [
    TRUE_CORRELATION,
    FALSE_CORRELATION,
    NULL_CORRELATION,
    WRONG_DIRECTION,
    TRUE_GROUP_DIFFERENCE,
    NULL_GROUP_DIFFERENCE,
    TRUE_TREND,
    NULL_TREND,
]


# --- claims the screen must refuse before any test runs -------------------

UNIVERSAL_CLAIM: Final = candidate(
    "c-universal",
    "bmi is always higher when age is higher",
    ClaimType.CORRELATION,
    ["age", "bmi"],
    direction=Direction.POSITIVE,
)

CAUSAL_CLAIM: Final = candidate(
    "c-causal",
    "age causes bmi to rise",
    ClaimType.CORRELATION,
    ["age", "bmi"],
    direction=Direction.POSITIVE,
)

DISTRIBUTION_CLAIM: Final = candidate(
    "c-distribution",
    "income is right-skewed",
    ClaimType.DISTRIBUTION,
    ["income", "area"],
)

MISSING_COLUMN_CLAIM: Final = candidate(
    "c-missing-column",
    "cholesterol is associated with age",
    ClaimType.CORRELATION,
    ["age", "cholesterol"],
    direction=Direction.POSITIVE,
)

WRONG_ARITY_CLAIM: Final = candidate(
    "c-wrong-arity",
    "bmi is associated with age and income",
    ClaimType.CORRELATION,
    ["age", "bmi", "income"],
    direction=Direction.POSITIVE,
)

INADMISSIBLE_CANDIDATES: Final[list[CandidateInsight]] = [
    UNIVERSAL_CLAIM,
    CAUSAL_CLAIM,
    DISTRIBUTION_CLAIM,
    MISSING_COLUMN_CLAIM,
    WRONG_ARITY_CLAIM,
]


def demo_batch() -> list[CandidateInsight]:
    """The acceptance-test batch (SCOPE.md 6): planted truths, a planted false
    correlation, nulls, and claims the screen must refuse -- all in one invocation,
    because BH only means anything when the whole family goes through together.
    """
    return [*TESTABLE_CANDIDATES, *INADMISSIBLE_CANDIDATES]
