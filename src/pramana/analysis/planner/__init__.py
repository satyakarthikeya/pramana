"""The planner: DeepSeek proposes an AnalysisSpec from exploration-split results; code decides.

`run_planner` is imported lazily so that importing the light models (which the exploration
ledger needs) does not pull in the tiers.
"""

from __future__ import annotations

from typing import Any

from pramana.analysis.planner.models import (
    AnalysisSpec,
    PlanDrop,
    PlannedMeasuredRequest,
    PlannerClaim,
    PlanRecord,
)

__all__ = [
    "AnalysisSpec",
    "PlanDrop",
    "PlanRecord",
    "PlannedMeasuredRequest",
    "PlannerClaim",
    "PlannerOutcome",
    "run_planner",
]


def __getattr__(name: str) -> Any:
    if name in {"run_planner", "PlannerOutcome"}:
        from pramana.analysis.planner import planner

        return getattr(planner, name)
    raise AttributeError(name)
