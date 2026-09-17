"""Data analysis module: raw dataset -> candidate insights.

Proposer role only. Nothing here may label an insight verified or true.

Covers data ingestion, cleaning, profiling, and candidate analysis.

Owner: P. Rohith
Scope: scope/SCOPE_P_Rohith.md
"""

from .cleaning import CleaningReport, clean_dataset
from .config import AnalysisConfig, load_config
from .hypotheses.generation import analyse, generate_candidates
from .ingestion import DatasetMetadata, get_dataset_metadata, load_dataset
from .profiling import profile_dataset
from .schema_inference import (
    ColumnProfile,
    ColumnRole,
    SchemaProfile,
    SemanticRefiner,
    describe_unusable,
    infer_schema,
    schema_profile,
)

__all__ = [
    "AnalysisConfig",
    "CleaningReport",
    "ColumnProfile",
    "ColumnRole",
    "DatasetMetadata",
    "SchemaProfile",
    "SemanticRefiner",
    "analyse",
    "clean_dataset",
    "describe_unusable",
    "generate_candidates",
    "get_dataset_metadata",
    "infer_schema",
    "load_config",
    "load_dataset",
    "profile_dataset",
    "schema_profile",
]
