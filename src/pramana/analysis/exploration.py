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
    """Run the configured engine and return its candidates with the exploration summary.

    `frame` must be the exploration rows. `shape` is the table's shape as the gateway will
    see it (the planner engine validates claims against it); it defaults to a classification
    of `frame`, which is only right when `frame` is the whole table.
    """
    engine = hypotheses.proposer.engine
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
