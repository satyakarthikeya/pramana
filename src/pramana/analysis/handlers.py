"""The analysis module's public handlers for the orchestration graph.

`orchestration/integration.py` loads these by import path
(`PRAMANA_INGEST_HANDLER=pramana.analysis.handlers:ingest`, and so on) and calls
each with a plain mapping, validating the mapping that comes back. Analysis never
imports orchestration (OWNERSHIP.md, direction of dependency): the request and
response shapes are the ones `integration.py` documents in `IngestRequest`,
`PreparationRequest`, `AnalysisRequest` and their results.

Every handler is a thin shell over a function that already exists here. None of
them adds analysis behaviour of its own.

Owner: P. Rohith
Scope: scope/SCOPE_P_Rohith.md
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import pandas as pd

from pramana.analysis.cleaning import clean_dataset
from pramana.analysis.config import load_config
from pramana.analysis.hypotheses.generation import analyse
from pramana.analysis.ingestion import load_dataset
from pramana.analysis.schema_inference import describe_unusable, infer_schema


def cleaned_dataset_ref(source_ref: str, frame: pd.DataFrame) -> str:
    """A reference naming the source AND the exact cleaned values.

    Guarantees: two frames with identical columns and values get the same reference,
    and any change to a value, a column name or the row order changes it. Candidates
    carry this reference, so a proof object can always be matched to the exact data
    it was computed on rather than to "whatever the file held at the time".
    """
    digest = hashlib.sha256()
    digest.update("\x1f".join(map(str, frame.columns)).encode("utf-8"))
    digest.update(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes())
    return f"{source_ref}#cleaned-sha256:{digest.hexdigest()[:16]}"


def ingest(request: Mapping[str, Any]) -> dict[str, Any]:
    """`IngestRequest` -> `IngestResult`: load the file `dataset_ref` names."""
    dataset_ref = str(request["dataset_ref"])
    return {"dataset": load_dataset(dataset_ref), "dataset_ref": dataset_ref}


def prepare(request: Mapping[str, Any]) -> dict[str, Any]:
    """`PreparationRequest` -> `PreparationResult`: clean, then profile the schema.

    The returned `dataset_ref` identifies the cleaned frame, not the raw file, and
    the schema profile carries the cleaning report and every unusable column with
    its reason, so nothing is dropped silently.
    """
    cleaned, report = clean_dataset(request["dataset"])
    schema = infer_schema(cleaned, load_config().schema_inference)
    profile = schema.model_dump(mode="json")
    profile["cleaning_report"] = report.model_dump(mode="json")
    profile["unusable_columns"] = describe_unusable(schema)
    return {
        "dataset": cleaned,
        "dataset_ref": cleaned_dataset_ref(str(request["dataset_ref"]), cleaned),
        "schema_profile": profile,
    }


def analyze(request: Mapping[str, Any]) -> dict[str, Any]:
    """`AnalysisRequest` -> `AnalysisResult`: propose one capped candidate batch."""
    _, candidates = analyse(request["dataset"], dataset_ref=str(request["dataset_ref"]))
    return {"candidate_insights": candidates}
