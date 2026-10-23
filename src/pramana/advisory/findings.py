"""The facts about one finding that the advisory steps may see, copied out of the results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    """A PASS finding as plain values. Holding a copy means nothing here can edit a proof."""

    insight_id: str
    claim: str
    claim_type: str
    variables: tuple[str, ...]
    direction: str | None
    reference_group: str | None
    q_value: float | None
    p_value: float | None
    effect_size: float | None
    effect_metric: str | None
    band: str | None
    n: int | None
    family_size: int | None
    alpha: float
