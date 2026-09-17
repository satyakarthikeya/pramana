"""Data analysis module: raw dataset -> candidate insights.

Proposer role only. Nothing here may label an insight verified or true.

Owner: P. Rohith
Scope: scope/SCOPE_P_Rohith.md
"""
"""Researcher 2 data ingestion, cleaning, profiling, and candidate analysis."""

from .cleaning import CleaningReport, clean_dataset
from .ingestion import DatasetMetadata, get_dataset_metadata, load_dataset
from .profiling import profile_dataset
from .public import analyze, ingest, prepare
from .schema_inference import infer_schema

__all__ = [
    "CleaningReport",
    "DatasetMetadata",
    "clean_dataset",
    "get_dataset_metadata",
    "load_dataset",
    "profile_dataset",
    "analyze",
    "ingest",
    "infer_schema",
    "prepare",
]
