"""Hypothesis generation strategies, all behind one common interface.

Owner: P. Rohith
Scope: scope/SCOPE_P_Rohith.md
"""

from .correlation import generate_correlation_candidates
from .group_difference import generate_group_difference_candidates
from .trend import generate_trend_candidates

__all__ = [
    "generate_correlation_candidates",
    "generate_group_difference_candidates",
    "generate_trend_candidates",
]
