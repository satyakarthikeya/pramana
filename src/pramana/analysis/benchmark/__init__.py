"""Evaluation dataset curation: the 40-dataset benchmark + the demo dataset.

Owner: P. Rohith
Scope: scope/SCOPE_P_Rohith.md
"""

from .contamination import ContaminationResult, screen_source
from .curation import BenchmarkManifest, DatasetRecord, curate_manifest
from .demo_dataset import build_demo_from_diabetes, create_demo_dataset

__all__ = [
    "BenchmarkManifest",
    "build_demo_from_diabetes",
    "ContaminationResult",
    "create_demo_dataset",
    "DatasetRecord",
    "curate_manifest",
    "screen_source",
]
