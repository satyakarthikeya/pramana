"""Data analysis module: raw dataset -> candidate insights.

Proposer role only. Nothing here may label an insight verified or true.

Covers data ingestion, cleaning, profiling, and candidate analysis.

Owner: P. Rohith
Scope: scope/SCOPE_P_Rohith.md
"""

from .cleaning import CleaningReport, clean_dataset
from .ingestion import DatasetMetadata, get_dataset_metadata, load_dataset
from .profiling import profile_dataset

__all__ = [
    "CleaningReport",
    "DatasetMetadata",
    "clean_dataset",
    "get_dataset_metadata",
    "load_dataset",
    "profile_dataset",
]
