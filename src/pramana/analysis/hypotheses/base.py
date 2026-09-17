"""Strategy interface: (dataframe, schema, config) -> list[CandidateInsight].
analysis_evidence carries the raw exploratory stat ONLY -- never a verdict.

What every strategy shares
---------------------------
`emit` is the single place a `CandidateInsight` is constructed. Every strategy goes
through it, so the guarantees below hold for all of them at once rather than three
times over:

  * the contract model is IMPORTED from `pramana.contracts`, never redefined
    (`OWNERSHIP.md`, analysis hard rule 1);
  * `variables` is `[x, y]` in the order the gateway's templates unpack it
    (`falsification/generator.py::_two_variables`), which for a group difference means
    the grouping column first and the measured column second -- the templates group by
    `VAR_X` and measure `VAR_Y`, so the reverse order would test a different claim;
  * `analysis_evidence` carries the exploratory statistic and the sample size and
    nothing that could be read as a verdict. No p-value, no "verified", no score.

Claim wording, and why it is templated
---------------------------------------
The gateway refuses universal wording ("always", "every") and causal verbs ("causes",
"leads to") before any code is generated, and it is right to. Claims here are built
from fixed hedged templates -- "is associated with", "tends to be higher in" -- so
they pass that screen by construction rather than by luck.

That leaves one hole this module cannot close alone: a column literally NAMED `all` or
`code_causes_x` would inject a screened term into an otherwise fine sentence. The
vocabulary lives in `verification/admissibility.py`, and analysis does not import
verification (`OWNERSHIP.md`, direction of dependency). `claim_screen` is the seam for
that: orchestration, which legitimately imports both, can pass the gateway's own
screen in, and a claim it refuses is dropped here instead of consuming a slot in the
BH family. With no screen supplied the candidate is still emitted -- the gateway
refuses it as `NOT_TESTABLE`, which is the correct outcome reached one step later.

Owner: P. Rohith (built by P.P. Satya Karthikeya -- team-agreed cross-module work)
Scope: scope/SCOPE_P_Rohith.md 2, component 4
"""

from __future__ import annotations

import re
from typing import Any, Protocol

import pandas as pd

from pramana.analysis.config import HypothesesConfig
from pramana.analysis.schema_inference import SchemaProfile
from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType, Direction

#: Characters an `insight_id` may keep. Anything else becomes `-`, so an id built from
#: a column called `BMI (kg/m^2)` is still a readable, log-safe token.
_ID_UNSAFE = re.compile(r"[^a-z0-9]+")


class ClaimScreen(Protocol):
    """A callable that decides whether a claim's WORDING is testable at all.

    The gateway's admissibility screen satisfies this shape. Supplying it here moves
    a refusal one step earlier, which is worth doing because a claim refused at the
    gateway still had to be built, transported and logged.
    """

    def __call__(self, claim: str, claim_type: ClaimType, variables: list[str]) -> bool:
        """True if the claim may be proposed."""
        ...


class HypothesisStrategy(Protocol):
    """One way of proposing candidates from a frame.

    Guarantees every implementation must hold:

      * it proposes, it never judges -- nothing it returns is marked verified, and
        `analysis_evidence` carries exploratory statistics only;
      * it reads roles from the `SchemaProfile` and touches no column whose
        `usable_for_hypotheses` is False;
      * it emits nothing at all when the data is too thin (`min_observations`),
        rather than a candidate the gateway could only call INCONCLUSIVE;
      * it is deterministic for a given `(frame, schema, config)`.
    """

    name: str

    def propose(
        self,
        frame: pd.DataFrame,
        schema: SchemaProfile,
        config: HypothesesConfig,
        *,
        dataset_ref: str,
        claim_screen: ClaimScreen | None = None,
    ) -> list[CandidateInsight]:
        """Candidates this strategy stands behind for `frame`."""
        ...


def slug(*parts: str) -> str:
    """A stable, readable, log-safe token built from `parts`.

    Guarantees: the same parts always produce the same slug, so an `insight_id` is
    reproducible across runs of the same data -- which is what lets a proof object be
    matched back to the candidate that produced it.
    """
    joined = "-".join(str(part) for part in parts)
    return _ID_UNSAFE.sub("-", joined.casefold()).strip("-") or "unnamed"


def usable_pair(
    frame: pd.DataFrame, x_column: str, y_column: str, min_observations: int
) -> pd.DataFrame | None:
    """The two columns with pairwise-incomplete rows dropped, or `None` if too thin.

    Guarantees: `None` whenever fewer than `min_observations` rows survive, or either
    column is constant among them. Dropping pairwise rather than filling matches what
    the gateway's templates do to the same pair, so the exploratory statistic reported
    in `analysis_evidence` describes the same rows the falsification test will see.

    A constant column is excluded because every association with it is exactly zero:
    proposing one spends a correction slot on an arithmetic certainty.
    """
    pair = frame[[x_column, y_column]].dropna()
    if len(pair) < min_observations:
        return None
    if pair[x_column].nunique() < 2 or pair[y_column].nunique() < 2:
        return None
    return pair


def emit(
    *,
    strategy: str,
    claim: str,
    claim_type: ClaimType,
    variables: list[str],
    dataset_ref: str,
    evidence: dict[str, Any],
    direction: Direction | None = None,
    reference_group: str | None = None,
    claim_screen: ClaimScreen | None = None,
) -> CandidateInsight | None:
    """Build one validated `CandidateInsight`, or `None` if it must not be proposed.

    Guarantees: the returned object is a `pramana.contracts.CandidateInsight` that
    passed that model's own validation -- the gateway needs no patching to accept it.
    `analysis_evidence` always carries `stat` and `raw_value` (the shape `PROJECT.md`
    5 names) plus `n_observations`, and never carries a p-value, a q-value or any
    field a reader could mistake for a verdict.

    Returns `None`, rather than raising, when `claim_screen` refuses the wording or
    when the contract itself refuses the candidate. Either is a claim that should not
    be proposed, and a generator that crashes mid-scan would lose the candidates it
    had already found.
    """
    if claim_screen is not None and not claim_screen(claim, claim_type, variables):
        return None

    forbidden = {"p_value", "q_value", "verdict", "evidence_score", "verified"}
    leaked = forbidden & set(evidence)
    if leaked:
        raise ValueError(
            f"analysis_evidence for {claim!r} carries verdict-shaped keys {sorted(leaked)}; "
            f"this module proposes and never judges (SCOPE_P 3)"
        )

    try:
        return CandidateInsight(
            insight_id=slug(strategy, *variables),
            claim=claim,
            claim_type=claim_type,
            variables=variables,
            dataset_ref=dataset_ref,
            analysis_evidence=dict(evidence),
            asserted_direction=direction,
            reference_group=reference_group,
        )
    except ValueError:
        # The contract refused it -- a duplicated column name, a blank id. Dropping
        # it is the fail-closed answer: the alternative is a malformed candidate
        # reaching the gateway, which is the failure this whole design exists to stop.
        return None
