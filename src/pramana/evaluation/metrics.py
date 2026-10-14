"""Precision, recall and empirical FDR, computed exactly from the planted truth table.

SPEC.md 3: the label set is complete, so every number here is a count ratio, not an
estimate. The scoring rule is fixed before any system runs. The rules SPEC.md does not
spell out are chosen conservatively and listed here, so nobody has to rediscover them
from the code (each is a decision for the team to confirm):

* **Direction is required.** A reported insight is a true positive only if it matches an
  injected relationship AND asserts its direction. Wrong direction is a false positive.
  An UNDIRECTED claim cannot be shown to have the right direction, so it is a false
  positive too; an analysis step that wants credit must assert a direction.
* **Claim type must be compatible.** A numeric pair accepts `correlation` or `trend`
  (both are monotonic claims on the same two columns); a shift accepts only
  `group_difference`. Anything else on an injected pair is a false positive.
* **Group direction is relative to the reference group.** A claim's `reference_group`
  defaults to the alphabetically first level, as the falsification template does, so
  "2.0 is lower" and "1.0 is higher" are the same finding.
* **Duplicates.** Each reported insight counts toward precision; recall counts each
  injected relationship once however often it is reported.
* **Nothing reported.** Precision is undefined (`None`), the false discovery proportion
  is 0 by the usual convention (V/R with R = 0), and the empirical FDR is the MEAN of the
  per-dataset proportions, which is the estimator of E[V/R * 1{R>0}] the BH guarantee is
  about. The pooled V/R is reported beside it.
* **Below-floor hits.** An injected relationship reported in the right direction is a
  true positive even when its effect sits in the NEGLIGIBLE band. Recall is broken down
  by effect level, which is the evidence that the schedule straddles the gate.

Owner: P.P. Satya Karthikeya
Scope: src/pramana/evaluation/SPEC.md 3
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType, Direction
from pramana.evaluation.config import RelationshipType, SignDirection
from pramana.evaluation.planted import GroundTruth, TruthRow

_NUMERIC_CLAIMS = frozenset({ClaimType.CORRELATION, ClaimType.TREND})


def claim_matches(row: TruthRow, candidate: CandidateInsight) -> bool:
    """True iff `candidate` reports the injected relationship `row` with its direction.

    Guarantees: a null row never matches; the variable set must equal the pair; the
    claim type must be compatible; the asserted direction must exist and equal the
    injected one (for a shift, expressed relative to the claim's reference group).
    """
    if row.label != "injected" or candidate.asserted_direction is None:
        return False
    if set(candidate.variables) != {row.var_a, row.var_b}:
        return False
    asserted = candidate.asserted_direction

    if row.relationship_type is RelationshipType.SHIFT:
        if candidate.claim_type is not ClaimType.GROUP_DIFFERENCE or not row.levels:
            return False
        reference = candidate.reference_group or sorted(row.levels)[0]
        if reference not in row.levels:
            return False
        injected_positive = row.direction is SignDirection.POSITIVE
        # Positive means the reference group is higher; naming the other level flips it.
        if reference != row.reference_group:
            injected_positive = not injected_positive
        return asserted is (Direction.POSITIVE if injected_positive else Direction.NEGATIVE)

    if candidate.claim_type not in _NUMERIC_CLAIMS:
        return False
    return asserted.value == row.direction.value


class DatasetScore(BaseModel):
    """One dataset's counts for one condition. Every ratio is derived from these."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_reported: int
    n_true_positive: int
    n_false_positive: int
    n_injected: int
    n_recovered: int
    injected_by_level: dict[str, int]
    recovered_by_level: dict[str, int]

    @property
    def precision(self) -> float | None:
        """TP / reported, or None when nothing was reported."""
        return self.n_true_positive / self.n_reported if self.n_reported else None

    @property
    def recall(self) -> float | None:
        """Recovered / injected, or None when nothing was injected."""
        return self.n_recovered / self.n_injected if self.n_injected else None

    @property
    def fdp(self) -> float:
        """False discovery proportion V/R, defined as 0 when nothing was reported."""
        return self.n_false_positive / self.n_reported if self.n_reported else 0.0


def score_reported(truth: GroundTruth, reported: Sequence[CandidateInsight]) -> DatasetScore:
    """Score the insights a condition REPORTED against the planted truth.

    Guarantees: exact (integer counts); `reported` is whatever the condition output --
    all proposals for A, the PASS set for D -- so the same function scores every arm.
    """
    injected = [row for row in truth.rows if row.label == "injected"]
    by_pair = {frozenset((row.var_a, row.var_b)): row for row in injected}
    recovered: set[frozenset[str]] = set()
    true_positive = 0
    for candidate in reported:
        row = by_pair.get(frozenset(candidate.variables))
        if row is not None and claim_matches(row, candidate):
            true_positive += 1
            recovered.add(frozenset((row.var_a, row.var_b)))
    injected_levels = Counter(row.effect_level for row in injected)
    recovered_levels = Counter(by_pair[pair].effect_level for pair in recovered)
    return DatasetScore(
        n_reported=len(reported),
        n_true_positive=true_positive,
        n_false_positive=len(reported) - true_positive,
        n_injected=len(injected),
        n_recovered=len(recovered),
        injected_by_level=dict(sorted(injected_levels.items())),
        recovered_by_level={k: recovered_levels.get(k, 0) for k in sorted(injected_levels)},
    )


class AggregateScore(BaseModel):
    """A condition's scores pooled over datasets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_datasets: int
    n_reported: int
    n_true_positive: int
    n_injected: int
    n_recovered: int
    precision: float | None
    recall: float | None
    mean_fdp: float
    pooled_fdp: float
    recall_by_level: dict[str, float]


def aggregate_scores(scores: Sequence[DatasetScore]) -> AggregateScore:
    """Pool counts across datasets (micro average); `mean_fdp` is the empirical FDR."""
    reported = sum(s.n_reported for s in scores)
    true_positive = sum(s.n_true_positive for s in scores)
    injected = sum(s.n_injected for s in scores)
    recovered = sum(s.n_recovered for s in scores)
    injected_levels: Counter[str] = Counter()
    recovered_levels: Counter[str] = Counter()
    for s in scores:
        injected_levels.update(s.injected_by_level)
        recovered_levels.update(s.recovered_by_level)
    return AggregateScore(
        n_datasets=len(scores),
        n_reported=reported,
        n_true_positive=true_positive,
        n_injected=injected,
        n_recovered=recovered,
        precision=true_positive / reported if reported else None,
        recall=recovered / injected if injected else None,
        mean_fdp=sum(s.fdp for s in scores) / len(scores) if scores else 0.0,
        pooled_fdp=(reported - true_positive) / reported if reported else 0.0,
        recall_by_level={
            level: recovered_levels[level] / count
            for level, count in sorted(injected_levels.items())
        },
    )
