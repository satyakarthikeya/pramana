"""Rank and cap candidates before they enter the verification batch."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pramana.contracts import CandidateInsight

from .hypotheses.base import evidence_value


def prioritize_candidates(
    candidates: Iterable[CandidateInsight],
    *,
    config: Mapping[str, int] | None = None,
    max_candidates: int = 100,
) -> list[CandidateInsight]:
    """Return a deterministic, bounded list ranked by exploratory effect magnitude."""

    limit = max_candidates if config is None else int(config.get("max_candidates", max_candidates))
    if limit < 1:
        raise ValueError("max_candidates must be at least 1")
    unique = {candidate.insight_id: candidate for candidate in candidates}
    return sorted(
        unique.values(),
        key=lambda candidate: (-evidence_value(candidate), candidate.insight_id),
    )[:limit]
