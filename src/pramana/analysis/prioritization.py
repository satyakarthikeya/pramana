"""Select one bounded, diverse batch of unverified candidates (Rohith, scope step 6)."""

from __future__ import annotations

import math
from collections.abc import Iterable

from pramana.analysis.config import HypothesesConfig
from pramana.contracts import CandidateInsight
from pramana.contracts.enums import ClaimType


def _rank(candidate: CandidateInsight) -> tuple[float, str]:
    """Rank finite exploratory magnitudes first, breaking ties by insight id."""
    raw = candidate.analysis_evidence.get("raw_value")
    magnitude = (
        abs(float(raw))
        if isinstance(raw, int | float) and not isinstance(raw, bool)
        else float("nan")
    )
    return (-magnitude if math.isfinite(magnitude) else math.inf, candidate.insight_id)


def prioritize_candidates(
    candidates: Iterable[CandidateInsight], *, config: HypothesesConfig
) -> list[CandidateInsight]:
    """Reserve strategy slots, then fill the shared cap by exploratory magnitude.

    Guarantees: one deterministic batch, unique ids, unchanged candidate objects,
    and at most max_candidates_per_run entries. Disabled strategies are excluded.
    Reservations are filled in rounds: each active strategy gets its strongest
    remaining candidate before any gets its second reserved slot. If the cap cannot
    fit a round, the strongest heads win, with id as the tie-breaker. Empty strategy
    allocations return to the shared pool. Missing/non-finite evidence ranks last.

    No expected demo outcomes, p-values, verification scores, or verdicts are read.
    This allocation is a proposal policy, not a statistical guarantee.
    """
    enabled = {ClaimType(name) for name, active in config.strategies.model_dump().items() if active}
    unique: dict[str, CandidateInsight] = {}
    for candidate in candidates:
        if candidate.claim_type not in enabled:
            continue
        previous = unique.get(candidate.insight_id)
        if previous is not None and previous != candidate:
            raise ValueError(f"conflicting candidates share insight_id {candidate.insight_id!r}")
        unique[candidate.insight_id] = candidate

    ranked = sorted(unique.values(), key=_rank)
    limit = config.max_candidates_per_run
    pools = {
        kind: [candidate for candidate in ranked if candidate.claim_type is kind]
        for kind in enabled
    }
    quotas = config.strategy_min_candidates.model_dump()
    positions = dict.fromkeys(enabled, 0)
    selected: dict[str, CandidateInsight] = {}

    while len(selected) < limit:
        heads = [
            pool[positions[kind]]
            for kind, pool in pools.items()
            if positions[kind] < min(quotas[kind.value], len(pool))
        ]
        if not heads:
            break
        for candidate in sorted(heads, key=_rank):
            if len(selected) == limit:
                break
            selected[candidate.insight_id] = candidate
            positions[candidate.claim_type] += 1

    for candidate in ranked:
        if len(selected) == limit:
            break
        selected.setdefault(candidate.insight_id, candidate)
    return sorted(selected.values(), key=_rank)
