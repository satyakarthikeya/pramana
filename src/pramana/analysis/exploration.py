"""One entry point for "look at the table and propose claims", with an honest account of how.

Whichever engine runs, the caller gets the candidates and an `ExplorationSummary`: how many
hypotheses were looked at, so the results can say what was screened versus what was
tested. This module chooses nothing statistical; it only routes to an engine and counts.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import pandas as pd

from pramana.analysis.config import HypothesesConfig
from pramana.analysis.hypotheses.base import ClaimScreen, record_scan
from pramana.analysis.hypotheses.generation import generate_candidates
from pramana.analysis.reader import DataBrief
from pramana.analysis.schema_inference import SchemaProfile
from pramana.analysis.shape import ShapeProfile, classify_shape
from pramana.analysis.workspace.agent import ChatFn, run_agent
from pramana.analysis.workspace.config import load_workspace_config
from pramana.analysis.workspace.ledger import ExplorationSummary
from pramana.contracts import CandidateInsight


def _engine_propose(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    hypotheses: HypothesesConfig,
    *,
    dataset_ref: str,
    run_id: UUID,
    brief: DataBrief | None = None,
    user_query: str | None = None,
    lesson_hints: Sequence[str] = (),
    claim_screen: ClaimScreen | None = None,
    chat: ChatFn | None = None,
    shape: ShapeProfile | None = None,
) -> tuple[list[CandidateInsight], ExplorationSummary]:
    """Run the configured engine and return its candidates with the exploration summary.

    `frame` must be the exploration rows. `shape` is the table's shape as the gateway will
    see it (the planner engine validates claims against it); it defaults to a classification
    of `frame`, which is only right when `frame` is the whole table.
    """
    engine = hypotheses.proposer.engine
    if engine == "deterministic":
        candidates, summary = insight_candidates(
            frame,
            schema,
            hypotheses,
            dataset_ref=dataset_ref,
            user_query=user_query,
            claim_screen=claim_screen,
        )
        if candidates:
            return candidates, summary
    if engine == "planner":
        # Imported here: the planner pulls in both analysis tiers, and only this engine needs it.
        from pramana.analysis.planner.planner import run_planner

        planned = run_planner(
            frame,
            schema,
            shape or classify_shape(frame, schema),
            config=hypotheses,
            run_id=run_id,
            dataset_ref=dataset_ref,
            chat=chat,
            brief=brief,
            user_query=user_query,
            claim_screen=claim_screen,
        )
        return planned.candidates, planned.exploration_summary
    if engine == "agent":
        outcome = run_agent(
            frame,
            schema,
            hypotheses,
            load_workspace_config(),
            dataset_ref=dataset_ref,
            run_id=run_id,
            brief=brief,
            user_query=user_query,
            lesson_hints=lesson_hints,
            claim_screen=claim_screen,
            chat=chat,
        )
        return outcome.candidates, outcome.exploration
    with record_scan() as scan:
        candidates = generate_candidates(
            frame,
            schema,
            hypotheses,
            dataset_ref=dataset_ref,
            claim_screen=claim_screen,
            run_id=run_id,
            user_query=user_query,
            lesson_hints=lesson_hints,
        )
    summary = ExplorationSummary(
        engine="api" if engine == "api" else "scan",
        examined=scan.total,
        proposed=len(candidates),
    )
    return candidates, summary


def insight_candidates(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    hypotheses: HypothesesConfig,
    *,
    dataset_ref: str,
    user_query: str | None = None,
    claim_screen: ClaimScreen | None = None,
) -> tuple[list[CandidateInsight], ExplorationSummary]:
    """Claims an analyst would test: the outcome's drivers, trends, the strongest links.

    `frame` is the exploration rows only, so the insights that choose the claims never see
    a row the gate will test on. Code writes every claim; nothing here is a verdict.
    """
    from pramana.analysis.hypotheses.llm_proposer import StructuredClaim, render_candidate
    from pramana.analysis.insights import build_insights

    report = build_insights(frame, schema, query=user_query)
    allowed = set(map(str, frame.columns))
    candidates: list[CandidateInsight] = []
    for claim in report.claims(hypotheses.max_candidates_per_run):
        candidate = render_candidate(
            StructuredClaim(
                claim_type=claim.claim_type,
                variables=list(claim.variables),
                direction=claim.direction,
                reference_group=claim.reference_group,
            ),
            frame,
            schema,
            hypotheses,
            dataset_ref=dataset_ref,
            allowed=allowed,
            claim_screen=claim_screen,
        )
        if candidate is not None and all(c.insight_id != candidate.insight_id for c in candidates):
            candidates.append(candidate)
    summary = ExplorationSummary(
        engine="scan", examined=len(report.insights), proposed=len(candidates)
    )
    return candidates, summary


def explore_and_propose(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    hypotheses: HypothesesConfig,
    *,
    dataset_ref: str,
    run_id: UUID,
    brief: DataBrief | None = None,
    user_query: str | None = None,
    lesson_hints: Sequence[str] = (),
    claim_screen: ClaimScreen | None = None,
    chat: ChatFn | None = None,
    shape: ShapeProfile | None = None,
) -> tuple[list[CandidateInsight], ExplorationSummary]:
    """Run the configured engine, then add the analyst's own claims it did not cover.

    A model engine proposes what the question or the column summaries suggest; the
    insights add what any analyst would check (the outcome's main drivers, a steady
    trend). Same-claim duplicates are dropped, and the family stays within its cap.
    """
    candidates, summary = _engine_propose(
        frame,
        schema,
        hypotheses,
        dataset_ref=dataset_ref,
        run_id=run_id,
        brief=brief,
        user_query=user_query,
        lesson_hints=lesson_hints,
        claim_screen=claim_screen,
        chat=chat,
        shape=shape,
    )
    if hypotheses.proposer.engine == "deterministic":
        return candidates, summary
    try:
        analyst, _ = insight_candidates(
            frame, schema, hypotheses, dataset_ref=dataset_ref, user_query=user_query,
            claim_screen=claim_screen,
        )
    except Exception:
        return candidates, summary
    # The analyst's claims go first: they come from computed rates and correlations, so
    # their direction is the one the rows show. A model's claim on the same pair of columns
    # (often a guessed direction) is dropped rather than tested twice.
    merged: list[CandidateInsight] = []
    pairs: set[frozenset[str]] = set()
    for candidate in [*analyst, *candidates]:
        pair = frozenset(candidate.variables)
        if pair in pairs:
            continue
        pairs.add(pair)
        merged.append(candidate)
    merged = merged[: hypotheses.max_candidates_per_run]
    return merged, summary.model_copy(update={"proposed": len(merged)})
