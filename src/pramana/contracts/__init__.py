"""Inter-module data contracts (PROJECT.md 5).

Every other module IMPORTS these models. Never redefine them locally.

Re-exported here so consumers write `from pramana.contracts import ProofObject` and
stay insulated from how the package is laid out internally.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md
"""

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import (
    ClaimType,
    Direction,
    EffectMetric,
    GateOutcome,
    TestType,
    Verdict,
)
from pramana.contracts.proof_object import ProofObject, ScoreComponents

__all__ = [
    "CandidateInsight",
    "ClaimType",
    "Direction",
    "EffectMetric",
    "GateOutcome",
    "ProofObject",
    "ScoreComponents",
    "TestType",
    "Verdict",
]
