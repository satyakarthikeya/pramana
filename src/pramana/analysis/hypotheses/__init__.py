"""Hypothesis generation strategies, all behind one common interface.

`generation.analyse` is the front door: frame in, `(SchemaProfile, list[CandidateInsight])`
out. The three strategy modules are exported for callers that want one scan only.

Owner: P. Rohith
Scope: scope/SCOPE_P_Rohith.md
"""

from pramana.analysis.hypotheses import correlation, group_difference, trend
from pramana.analysis.hypotheses.base import ClaimScreen, HypothesisStrategy, emit, usable_pair
from pramana.analysis.hypotheses.generation import analyse, generate_candidates

__all__ = [
    "ClaimScreen",
    "HypothesisStrategy",
    "analyse",
    "correlation",
    "emit",
    "generate_candidates",
    "group_difference",
    "trend",
    "usable_pair",
]
