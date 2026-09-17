"""Evaluation dataset curation: the 40-dataset benchmark + the demo dataset.

Owner: P. Rohith
Scope: scope/SCOPE_P_Rohith.md
"""

from .contamination import ContaminationResult, screen_source
from .curation import BenchmarkManifest, DatasetRecord, curate_manifest

__all__ = [
    "BenchmarkManifest",
    "ContaminationResult",
    "DatasetRecord",
    "curate_manifest",
    "screen_source",
]
