"""Falsification attacks: deterministic attempts to break a finding after it passed (PLAN §7).

Owner: P.P. Satya Karthikeya
Scope: PLAN_analysis_platform.md P5
"""

from pramana.verification.attacks.runner import AttacksConfig, ClaimView, run_attacks

__all__ = ["AttacksConfig", "ClaimView", "run_attacks"]
