"""Falsification attacks: deterministic attempts to break a finding after it passed (PLAN §7).

Owner: P.P. Satya Karthikeya
Scope: PLAN_analysis_platform.md P5
"""

from pramana.verification.attacks.runner import (
    AttackHints,
    AttacksConfig,
    ClaimView,
    run_attacks,
)

__all__ = ["AttackHints", "AttacksConfig", "ClaimView", "run_attacks"]
