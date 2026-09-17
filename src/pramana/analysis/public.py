"""Public analysis entrypoints used by the orchestration integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from pramana.contracts import CandidateInsight

from .cleaning import clean_dataset
from .ingestion import get_dataset_metadata, load_dataset
from .hypotheses import (
    generate_correlation_candidates,
    generate_group_difference_candidates,
    generate_trend_candidates,
)
from .prioritization import prioritize_candidates
from .profiling import profile_dataset
from .schema_inference import infer_schema


def ingest(path: str | Path) -> dict[str, Any]:
    """Load an upload and return the frame plus a worker-readable source reference."""

    source = Path(path).resolve()
    dataset = load_dataset(source)
    return {
        "dataset": dataset,
        "dataset_ref": str(source),
        "metadata": get_dataset_metadata(dataset, source_path=source).model_dump(
            by_alias=True
        ),
    }


def prepare(payload: Mapping[str, Any] | pd.DataFrame) -> dict[str, Any]:
    """Clean a frame, persist it at a shared path, and return its schema profile."""

    if isinstance(payload, pd.DataFrame):
        dataset = payload
        source_ref = "in_memory_dataset"
    else:
        dataset = payload.get("dataset")
        source_ref = str(payload.get("dataset_ref", "in_memory_dataset"))
    if not isinstance(dataset, pd.DataFrame):
        raise TypeError("prepare requires a pandas DataFrame in the dataset field")

    cleaned, report = clean_dataset(dataset)
    source = Path(source_ref)
    output = source.with_name(f"{source.stem}.cleaned.pkl") if source.suffix else source
    if source_ref == "in_memory_dataset":
        output = Path("data") / "interim" / "prepared_dataset.cleaned.pkl"
    output.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_pickle(output)
    schema_profile = infer_schema(cleaned)
    schema_profile["profile"] = profile_dataset(cleaned)
    return {
        "dataset": cleaned,
        "dataset_ref": str(output.resolve()),
        "schema_profile": schema_profile,
        "cleaning_report": report.model_dump(),
    }


def analyze(
    payload: Mapping[str, Any] | pd.DataFrame,
    *,
    config: Mapping[str, int] | None = None,
) -> dict[str, list[CandidateInsight]]:
    """Generate unverified CandidateInsight proposals from one prepared frame."""

    if isinstance(payload, pd.DataFrame):
        dataset = payload
        dataset_ref = "in_memory_dataset"
        schema_profile = infer_schema(dataset)
    else:
        dataset = payload.get("dataset")
        dataset_ref = str(payload.get("dataset_ref", ""))
        schema_profile = payload.get("schema_profile") or infer_schema(dataset)
    if not isinstance(dataset, pd.DataFrame):
        raise TypeError("analyze requires a pandas DataFrame in the dataset field")
    if not dataset_ref:
        raise ValueError("analyze requires the exact cleaned dataset_ref")

    candidates = [
        *generate_correlation_candidates(dataset, schema_profile, dataset_ref),
        *generate_group_difference_candidates(dataset, schema_profile, dataset_ref),
        *generate_trend_candidates(dataset, schema_profile, dataset_ref),
    ]
    return {
        "candidate_insights": prioritize_candidates(candidates, config=config),
    }
