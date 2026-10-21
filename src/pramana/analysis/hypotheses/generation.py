"""The analysis agent's output: one frame in, one batch of `CandidateInsight`s out.

This is `PROJECT.md` workflow step [2] and `SCOPE_P_Rohith.md` 4 step 4 -- the handoff
into the verification gateway. Everything downstream of here assumes the batch is
complete, because BH-FDR is applied once across the whole family (`AGENTS.md` 3.2): a
candidate emitted in a second call would be corrected against a different family size
and get a different q-value for the same data.

Why the cap lives here
-----------------------
`max_candidates_per_run` is not a nicety. Benjamini-Hochberg divides by the family
size, so an unbounded scan of a 60-column frame (1,770 correlation pairs alone) makes
every genuine finding harder to pass in proportion to how many junk pairs were scanned
alongside it. Capping is how the proposer avoids poisoning its own signal.

The selector reserves configured slots per strategy, then fills the remaining cap
by exploratory magnitude. This is a ranking rule, not a verdict: a candidate that
survives the cap has not been judged, and a dropped candidate has not been refuted.

Owner: P. Rohith (built by P.P. Satya Karthikeya -- team-agreed cross-module work)
Scope: scope/SCOPE_P_Rohith.md 2, component 4
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import pandas as pd

from pramana.analysis.config import AnalysisConfig, HypothesesConfig, load_config
from pramana.analysis.hypotheses import correlation, group_difference, trend
from pramana.analysis.hypotheses.base import ClaimScreen
from pramana.analysis.prioritization import prioritize_candidates
from pramana.analysis.schema_inference import SchemaProfile, infer_schema
from pramana.contracts.candidate_insight import CandidateInsight

#: Strategy name -> (toggle attribute on `StrategyToggles`, propose function). Ordered,
#: so a run's candidate list is reproducible before the cap is applied.
_STRATEGIES = (
    ("correlation", correlation.propose),
    ("group_difference", group_difference.propose),
    ("trend", trend.propose),
)


def generate_candidates(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    config: HypothesesConfig,
    *,
    dataset_ref: str,
    claim_screen: ClaimScreen | None = None,
    run_id: str | UUID | None = None,
    user_query: str | None = None,
    lesson_hints: Sequence[str] = (),
) -> list[CandidateInsight]:
    """Run every enabled strategy over `frame` and return one capped batch.

    Guarantees:

      * every element is a `pramana.contracts.CandidateInsight` that passed that
        model's own validation -- the gateway accepts the batch unpatched;
      * `insight_id` is unique within the batch, which is what `CandidateInsight`
        means by "unique per run" and what BH-FDR needs to key results by;
      * no candidate rests on fewer than `config.min_observations` usable rows, nor
        on a column schema inference could not confidently classify;
      * `len(result) <= config.max_candidates_per_run`;
      * nothing in the batch is marked verified, and no `analysis_evidence` carries a
        p-value, a q-value or a verdict. This module proposes; the gateway judges.

    The result is deterministic for a given `(frame, schema, config)`: strategies run
    in a fixed order, and the cap breaks ties on `insight_id` so an equal-effect pair
    cannot swap places between runs.
    """
    if config.proposer.engine == "api":
        from pramana.analysis.hypotheses.llm_proposer import generate_llm_candidates

        return generate_llm_candidates(
            frame,
            schema,
            config,
            dataset_ref=dataset_ref,
            run_id=run_id,
            user_query=user_query,
            lesson_hints=lesson_hints,
            claim_screen=claim_screen,
        )
    if config.proposer.engine != "deterministic":
        raise ValueError("Unsupported analysis engine; no deterministic fallback")
    toggles = config.strategies
    candidates: list[CandidateInsight] = []
    seen: set[str] = set()

    for name, propose in _STRATEGIES:
        if not getattr(toggles, name):
            continue
        for candidate in propose(
            frame, schema, config, dataset_ref=dataset_ref, claim_screen=claim_screen
        ):
            # Two strategies should never collide on an id, but a batch with a
            # duplicate would silently give one claim two q-values downstream.
            if candidate.insight_id in seen:
                continue
            seen.add(candidate.insight_id)
            candidates.append(candidate)

    return prioritize_candidates(candidates, config=config)


def analyse(
    frame: pd.DataFrame,
    *,
    dataset_ref: str,
    config: AnalysisConfig | None = None,
    claim_screen: ClaimScreen | None = None,
    run_id: str | UUID | None = None,
    user_query: str | None = None,
    lesson_hints: Sequence[str] = (),
) -> tuple[SchemaProfile, list[CandidateInsight]]:
    """Infer the schema and propose candidates in one call -- the module's front door.

    Guarantees: the schema the candidates were built from is returned alongside them,
    so a caller can report exactly which columns were skipped and why
    (`schema_inference.describe_unusable`) rather than discovering a silent exclusion
    later. `frame` is never modified. With `config` omitted, every threshold comes
    from `configs/analysis.yaml`.
    """
    resolved = config if config is not None else load_config()
    schema = infer_schema(frame, resolved.schema_inference)
    candidates = generate_candidates(
        frame,
        schema,
        resolved.hypotheses,
        dataset_ref=dataset_ref,
        claim_screen=claim_screen,
        run_id=run_id,
        user_query=user_query,
        lesson_hints=lesson_hints,
    )
    return schema, candidates
