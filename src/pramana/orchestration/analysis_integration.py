"""Thin adapters from graph state to the analysis package's public API.

The analysis package owns every data decision.  This module only translates graph
state, persists the exact cleaned frame for the worker, and maps public analysis
results back into state.  Keeping that boundary here lets orchestration consume the
analysis implementation already present on ``main`` without requiring an additional
handler module in another owner's package.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pandas as pd

from pramana.common.logging import get_logger
from pramana.common.paths import DATA_DIR
from pramana.contracts import DataStructure, TableShape
from pramana.orchestration.adapters import StateAdapter
from pramana.orchestration.state import PramanaState


@dataclass(frozen=True)
class AnalysisNodeAdapters:
    """The three analysis-owned operations consumed by graph nodes."""

    ingest: StateAdapter
    prepare: StateAdapter
    analyze: StateAdapter


def _require_frame(value: Any, operation: str) -> pd.DataFrame:
    """Return a dataframe or refuse an invalid analysis boundary value."""
    if not isinstance(value, pd.DataFrame):
        raise TypeError(f"{operation} requires a pandas DataFrame")
    return value


def _persist_cleaned_frame(frame: pd.DataFrame, run_id: UUID, data_dir: Path) -> str:
    """Atomically persist the exact frame candidate generation and verification share."""
    run_dir = data_dir.resolve() / "runs" / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "cleaned.pkl"
    temporary = run_dir / f".{target.name}.{uuid4().hex}.tmp"
    try:
        frame.to_pickle(temporary)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return str(target.resolve())


def data_structure_for(frame: pd.DataFrame, schema: Any) -> DataStructure:
    """The table's shape as the gate needs it, from the analysis shape classifier."""
    from pramana.analysis.shape import classify_shape

    shape = classify_shape(frame, schema)
    period = shape.period if shape.time_column else None
    return DataStructure(
        shape=TableShape(shape.shape.value),
        time_column=shape.time_column,
        entity_column=shape.entity_column if shape.time_column else None,
        period=period,
        declared_by="shape_classifier",
    )


def exploration_rows(frame: pd.DataFrame, structure: DataStructure) -> pd.DataFrame:
    """The exploration split of `frame`: no row the gate will test on."""
    from pramana.verification.config import load_config as load_verification_config
    from pramana.verification.schemes import exploration_frame

    return exploration_frame(frame, structure, load_verification_config())[0]


def run_planned_measured(
    frame: pd.DataFrame, schema: Any, shape: Any, requests: list[Any]
) -> Any:
    """The planner's accepted Measured requests, run on the whole cleaned table.

    Guarantees: only requests the planner already linted and accepted are run, through
    the Measured tier's closed menu; a failure is logged and gives None, never a partial
    result. Nothing here becomes a claim, a verdict or a memory.
    """
    from pramana.analysis.measured import compute_measured
    from pramana.analysis.measured.models import MeasuredRequest

    try:
        return compute_measured(
            frame,
            schema,
            shape,
            requests=[
                MeasuredRequest(
                    task=r.task, target=r.target, features=list(r.features),
                    controls=list(r.controls),
                )
                for r in requests
            ],
        )
    except Exception as error:  # a failed model fit must not take the run down
        get_logger(component="planned-measured").warning(
            "planned_measured_failed", error_type=type(error).__name__, error=str(error)
        )
        return None


def drop_oversize_trends(
    candidates: list[Any], exploration: Any, n_rows: int
) -> tuple[list[Any], Any]:
    """Leave out trend claims on a table above the Sen-slope row ceiling.

    The ceiling is a memory limit of the trend effect size, not a statistical choice, and
    rows are never sampled silently. Every other claim is still tested, and each trend
    claim left out is recorded with its reason where the report shows dropped claims.
    """
    from pramana.analysis.planner.models import PlanDrop
    from pramana.verification.stats.effect_size import MAX_SENS_SLOPE_OBSERVATIONS

    if n_rows <= MAX_SENS_SLOPE_OBSERVATIONS:
        return candidates, exploration
    left_out = [c for c in candidates if c.claim_type == "trend"]
    if not left_out:
        return candidates, exploration
    reason = (
        f"a trend test supports at most {MAX_SENS_SLOPE_OBSERVATIONS:,} rows and this table "
        f"has {n_rows:,}; the trend is described in the report instead"
    )
    kept = [c for c in candidates if c.claim_type != "trend"]
    update: dict[str, Any] = {"proposed": len(kept)}
    if exploration.plan is not None:
        ids = {c.insight_id for c in left_out}
        drops = [
            PlanDrop(
                what="claim",
                item=f"trend({', '.join(c.variables)})",
                reason_code="wrong_shape",
                reason=reason[:400],
            )
            for c in left_out
        ]
        update["plan"] = exploration.plan.model_copy(
            update={
                "dropped": [*exploration.plan.dropped, *drops],
                "accepted_claims": [
                    a for a in exploration.plan.accepted_claims if a.insight_id not in ids
                ],
            }
        )
    return kept, exploration.model_copy(update=update)


def native_analysis_adapters(
    *, data_dir: Path | None = None, candidate_limit: int | None = None
) -> AnalysisNodeAdapters:
    """Use Rohith's current public analysis API behind graph-compatible callables.

    The returned adapters guarantee that candidate generation and downstream
    verification refer to the same persisted cleaned dataframe.  No insight is
    labelled PASS or REJECT here; the verification gateway remains the only judge.
    """
    from pramana.analysis import (
        SchemaProfile,
        clean_dataset,
        get_dataset_metadata,
        infer_schema,
        load_config,
        load_dataset,
        profile_dataset,
    )
    from pramana.analysis.exploration import explore_and_propose
    from pramana.analysis.reader import read_data

    artifact_root = (data_dir or DATA_DIR).resolve()
    analysis_config = load_config()
    if any(os.getenv(name) for name in ("PRAMANA_ANALYSIS_BASE_URL", "PRAMANA_ANALYSIS_MODEL")):
        raise ValueError(
            "Legacy local analysis settings are unsupported; use DEEPSEEK_BASE_URL "
            "and DEEPSEEK_MODEL (or PRAMANA_ANALYSIS_API_BASE_URL / _API_MODEL)"
        )
    hypotheses = analysis_config.hypotheses
    if candidate_limit is not None:
        hypotheses = type(hypotheses).model_validate(
            {
                **hypotheses.model_dump(),
                "max_candidates_per_run": min(candidate_limit, hypotheses.max_candidates_per_run),
            }
        )

    def ingest(state: PramanaState) -> dict[str, Any]:
        if not state.dataset_ref:
            raise ValueError("dataset_ref is required before ingestion")
        source = Path(state.dataset_ref).resolve()
        frame = load_dataset(source)
        metadata = get_dataset_metadata(frame, source_path=source)
        return {
            "dataset": frame,
            "dataset_ref": str(source),
            "dataset_metadata": metadata.model_dump(mode="json", by_alias=True),
        }

    def prepare(state: PramanaState) -> dict[str, Any]:
        frame = _require_frame(state.dataset, "preparation")
        cleaned, cleaning_report = clean_dataset(frame)
        cleaned_ref = _persist_cleaned_frame(cleaned, state.run_id, artifact_root)
        schema = infer_schema(cleaned, analysis_config.schema_inference)
        return {
            "data_structure": data_structure_for(cleaned, schema),
            "dataset": cleaned,
            "dataset_ref": cleaned_ref,
            "cleaning_report": cleaning_report.model_dump(mode="json"),
            "dataset_profile": profile_dataset(cleaned),
            "schema_profile": schema.model_dump(mode="json"),
        }

    def analyze(state: PramanaState) -> dict[str, Any]:
        frame = _require_frame(state.dataset, "candidate generation")
        if not state.dataset_ref:
            raise ValueError("cleaned dataset_ref is required before candidate generation")
        schema = SchemaProfile.model_validate(state.schema_profile)
        whole = frame
        shape = None
        if hypotheses.proposer.engine == "planner":
            from pramana.analysis.shape import classify_shape

            # The planner validates claims against the table's shape; classify the whole
            # cleaned table, exactly as `prepare` did for the gateway.
            shape = classify_shape(frame, schema)
        if state.data_structure is not None:
            # The proposer never sees a confirmation row (PLAN D5).
            frame = exploration_rows(frame, state.data_structure)
        candidates, exploration = explore_and_propose(
            frame,
            schema,
            hypotheses,
            dataset_ref=state.dataset_ref,
            run_id=state.run_id,
            brief=read_data(frame, schema),
            user_query=state.user_query,
            lesson_hints=state.lesson_hints,
            shape=shape,
        )
        candidates, exploration = drop_oversize_trends(candidates, exploration, len(whole))
        update: dict[str, Any] = {
            "candidate_insights": candidates,
            "exploration": exploration.model_dump(mode="json"),
        }
        if exploration.measured_requests and shape is not None:
            planned = run_planned_measured(whole, schema, shape, exploration.measured_requests)
            if planned is not None:
                update["planned_measured"] = planned.model_dump(mode="json")
        return update

    return AnalysisNodeAdapters(ingest=ingest, prepare=prepare, analyze=analyze)
