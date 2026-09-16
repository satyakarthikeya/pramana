"""The admissibility screen -- the gateway's first step, before any code is generated.

Why a screen exists at all: a permutation test answers exactly one question, "could
the null have produced this?", and there are perfectly sensible English sentences it
cannot answer no matter how small the p-value gets.

  * "X is ALWAYS higher when Y is higher" -- a universal claim. The test compares an
    observed statistic against a shuffled null. It can support "tends to be higher".
    A single counter-example refutes "always", and no amount of aggregate evidence
    establishes it. Passing such a sentence would produce a proof object that proves
    strictly less than the sentence it is attached to.
  * "X CAUSES Y" -- the data is observational. No p-value licenses a causal verb;
    that needs a design (randomisation, an instrument), not a statistic.

Refusing these BEFORE testing is deliberate. If they were tested and then refused,
the refusal reason would depend on the data, which is a decision made after peeking.
Screening on the claim alone keeps the decision independent of the numbers.

Screened claims are NOT members of the BH family (PROJECT.md 2). They consumed no
test, so counting them would inflate the correction and make every real claim harder
to pass for no reason.

The vocabulary lives here in code rather than in `configs/verification.yaml`. The
config holds thresholds -- numbers that are legitimately tuned per run. This is not a
threshold; loosening it changes what the gateway is willing to claim, which is a
design decision that belongs in review, not in a YAML edit.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 2 component 0
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType

#: Words that turn a statistical tendency into a universal law. Matched on word
#: boundaries so "small" does not trip "all" and "nonetheless" does not trip "none".
UNIVERSAL_TERMS: frozenset[str] = frozenset(
    {
        "always",
        "never",
        "all",
        "every",
        "everyone",
        "none",
        "no one",
        "nobody",
        "guarantees",
        "guaranteed",
        "invariably",
        "without exception",
    }
)

#: Verbs that assert a mechanism rather than an association. Observational data
#: cannot support any of them.
CAUSAL_TERMS: frozenset[str] = frozenset(
    {
        "causes",
        "cause",
        "caused",
        "causing",
        "leads to",
        "lead to",
        "leading to",
        "makes",
        "make",
        "making",
        "results in",
        "resulting in",
        "due to",
        "because of",
        "the effect of",
    }
)

#: Claim types the template renderer can build a falsification for (SCOPE.md 4 step 8).
#: `distribution` is deliberately absent: no template exists in this scope, and the
#: rule is fail-closed, not "fall back to something generic" (SCOPE.md 4 step 6).
TESTABLE_CLAIM_TYPES: frozenset[ClaimType] = frozenset(
    {ClaimType.CORRELATION, ClaimType.GROUP_DIFFERENCE, ClaimType.TREND}
)

#: Every supported claim type is a relationship between exactly two columns.
REQUIRED_VARIABLE_COUNT = 2


class AdmissibilityResult(BaseModel):
    """Whether a claim may be tested, and if not, why not.

    Guarantees: `reason` is non-empty exactly when `admissible` is False. The reason
    is written for the analysis agent to act on, so it names the offending term or
    column rather than saying "invalid claim".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    admissible: bool
    reason: str | None = Field(
        default=None, description="Why the claim was refused. Null iff admissible."
    )

    def model_post_init(self, __context: object) -> None:
        if self.admissible and self.reason is not None:
            raise ValueError("an admissible claim must not carry a refusal reason")
        if not self.admissible and not (self.reason or "").strip():
            raise ValueError("a refused claim must carry a non-empty reason")


ADMISSIBLE = AdmissibilityResult(admissible=True)


def _matched_terms(text: str, vocabulary: Iterable[str]) -> list[str]:
    """Terms from `vocabulary` present in `text`, matched on word boundaries."""
    lowered = text.lower()
    hits = [
        term
        for term in vocabulary
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered) is not None
    ]
    return sorted(hits)


def screen(candidate: CandidateInsight, columns: Sequence[str]) -> AdmissibilityResult:
    """Decide whether `candidate` is testable at all, without looking at any data.

    Guarantees: the decision depends only on the claim and the column NAMES -- never
    on the values, so it cannot be influenced by the result it would have produced.
    The checks run in a fixed order and the first failure wins, so the reason is
    deterministic for a given claim.

    `columns` is the cleaned dataframe's column list. Testing a claim about a column
    that is not there would crash the executor; refusing it here is the same verdict
    reached honestly and 60 seconds earlier.
    """
    if candidate.claim_type not in TESTABLE_CLAIM_TYPES:
        supported = ", ".join(sorted(TESTABLE_CLAIM_TYPES))
        return AdmissibilityResult(
            admissible=False,
            reason=(
                f"claim_type '{candidate.claim_type}' has no falsification template in this "
                f"scope; supported types are {supported}. Fail-closed rather than "
                f"substituting a generic test (SCOPE.md 4 step 8)."
            ),
        )

    universal_hits = _matched_terms(candidate.claim, UNIVERSAL_TERMS)
    if universal_hits:
        return AdmissibilityResult(
            admissible=False,
            reason=(
                f"claim uses universal wording {universal_hits}: a permutation test can "
                f"support 'tends to be higher', never 'always'. Restate as a tendency "
                f"(for example 'is associated with', 'tends to be higher in')."
            ),
        )

    causal_hits = _matched_terms(candidate.claim, CAUSAL_TERMS)
    if causal_hits:
        return AdmissibilityResult(
            admissible=False,
            reason=(
                f"claim uses causal wording {causal_hits} on observational data: no p-value "
                f"licenses a causal verb. Restate as an association."
            ),
        )

    if len(candidate.variables) != REQUIRED_VARIABLE_COUNT:
        return AdmissibilityResult(
            admissible=False,
            reason=(
                f"claim names {len(candidate.variables)} variables; every supported claim "
                f"type is a relationship between exactly {REQUIRED_VARIABLE_COUNT} columns."
            ),
        )

    known = set(columns)
    missing = [column for column in candidate.variables if column not in known]
    if missing:
        return AdmissibilityResult(
            admissible=False,
            reason=(
                f"columns {sorted(missing)} are not in the cleaned dataframe; "
                f"available columns are {sorted(known)}."
            ),
        )

    return ADMISSIBLE
