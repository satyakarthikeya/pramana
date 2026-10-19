"""Explicit memory settings; storage failure never selects a fallback."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pramana.common.config import load_yaml
from pramana.common.paths import DATA_DIR


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ChromaSettings(Settings):
    mode: Literal["persistent", "http"]
    host: str
    port: int = Field(gt=0, le=65535)
    collection: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,62}$")
    persist_path: str
    embedding_model: Literal["all-MiniLM-L6-v2"]


class RetrievalSettings(Settings):
    top_k: int = Field(gt=0, le=100)
    min_similarity: float = Field(ge=-1, le=1)
    verified_only: Literal[True]


class APISettings(Settings):
    host: str
    port: int = Field(gt=0, le=65535)
    max_upload_mb: int = Field(gt=0)
    max_active_runs: int = Field(gt=0)
    verification_mode: Literal["celery", "inprocess"]


class MemorySettings(Settings):
    chroma: ChromaSettings
    retrieval: RetrievalSettings
    api: APISettings


def load_memory_settings() -> MemorySettings:
    """Load owner-specific config with explicit local/server overrides."""
    values = load_yaml("memory")
    for key, env in {
        "mode": "PRAMANA_CHROMA_MODE",
        "host": "CHROMA_HOST",
        "port": "CHROMA_PORT",
        "persist_path": "PRAMANA_CHROMA_PATH",
    }.items():
        if value := os.getenv(env):
            values["chroma"][key] = value
    if value := os.getenv("PRAMANA_API_VERIFICATION_MODE"):
        values["api"]["verification_mode"] = value
    return MemorySettings.model_validate(values)


def persistent_path(settings: ChromaSettings) -> Path:
    """Resolve relative memory paths below the shared data directory."""
    path = Path(settings.persist_path)
    return path if path.is_absolute() else DATA_DIR / path
