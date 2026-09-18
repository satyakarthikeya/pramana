"""Thin adapters from graph state to the analysis package's public API.

The analysis package owns every data decision.  This module only translates graph
state, persists the exact cleaned frame for the worker, and maps public analysis
results back into state.  Keeping that boundary here lets orchestration consume the
analysis implementation already present on ``main`` without requiring an additional
handler module in another owner's package.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pandas as pd

from pramana.common.paths import DATA_DIR
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


def native_analysis_adapters(*, data_dir: Path | None = None) -> AnalysisNodeAdapters:
    """Use Rohith's current public analysis API behind graph-compatible callables.

    The returned adapters guarantee that candidate generation and downstream
    verification refer to the same persisted cleaned dataframe.  No insight is
    labelled PASS or REJECT here; the verification gateway remains the only judge.
    """
    from pramana.analysis import (
        SchemaProfile,
        clean_dataset,
        generate_candidates,
        get_dataset_metadata,
        infer_schema,
        load_config,
        load_dataset,
        profile_dataset,
    )

    artifact_root = (data_dir or DATA_DIR).resolve()
    analysis_config = load_config()

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
        candidates = generate_candidates(
            frame,
            schema,
            analysis_config.hypotheses,
            dataset_ref=state.dataset_ref,
        )
        return {"candidate_insights": candidates}

    return AnalysisNodeAdapters(ingest=ingest, prepare=prepare, analyze=analyze)
