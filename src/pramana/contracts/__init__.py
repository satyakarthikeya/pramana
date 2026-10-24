"""Inter-module data contracts (PROJECT.md 5).

Every other module IMPORTS these models. Never redefine them locally.

Re-exported here so consumers write `from pramana.contracts import ProofObject` and
stay insulated from how the package is laid out internally.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md
"""

from pramana.contracts.attack import AttackOutcome, AttackResult
from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import (
    ClaimType,
    Direction,
    EffectMetric,
    GateOutcome,
    PermutationScheme,
    TableShape,
    TestType,
    Verdict,
)
from pramana.contracts.interval import EffectInterval
from pramana.contracts.power import PowerNote
from pramana.contracts.proof_object import ProofObject, ScoreComponents
from pramana.contracts.structure import DataStructure, SplitRecord

__all__ = [
    "AttackOutcome",
    "AttackResult",
    "CandidateInsight",
    "ClaimType",
    "DataStructure",
    "Direction",
    "EffectInterval",
    "EffectMetric",
    "GateOutcome",
    "PermutationScheme",
    "PowerNote",
    "ProofObject",
    "ScoreComponents",
    "SplitRecord",
    "TableShape",
    "TestType",
    "Verdict",
]
