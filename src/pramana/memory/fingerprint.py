"""Dataset fingerprinting / profiling used as the retrieval key.

Owner: M. Karthik Reddy
Scope: scope/SCOPE_M_Karthik_Reddy.md
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pramana.analysis.schema_inference import SchemaProfile


def _describe(columns: dict[str, str]) -> tuple[str, str]:
    canonical = json.dumps(columns, sort_keys=True, ensure_ascii=True)
    counts = Counter(columns.values())
    description = "Dataset schema. " + "; ".join(
        f"{name}: {role}" for name, role in sorted(columns.items())
    )
    description += ". Roles: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    return hashlib.sha256(canonical.encode()).hexdigest(), description


class DatasetFingerprint(BaseModel):
    """Identify a schema without participant records or category values."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    columns: dict[str, str] = Field(min_length=1)
    digest: str
    description: str

    @model_validator(mode="after")
    def consistent_description(self) -> DatasetFingerprint:
        digest, description = _describe(self.columns)
        if self.digest != digest or self.description != description:
            raise ValueError("fingerprint does not match its schema")
        return self


def fingerprint_schema(schema: SchemaProfile) -> DatasetFingerprint:
    """Return a deterministic schema key excluding ID-like and unusable columns."""
    columns = {
        name: profile.role.value
        for name, profile in schema.columns.items()
        if profile.usable_for_hypotheses and profile.role.value not in {"unknown", "id_like"}
    }
    if not columns:
        raise ValueError("no usable schema columns for a memory fingerprint")
    digest, description = _describe(columns)
    return DatasetFingerprint(columns=columns, digest=digest, description=description)
