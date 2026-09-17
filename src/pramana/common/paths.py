"""Canonical, side-effect-free paths used throughout PRAMANA."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "configs"
DATA_DIR = Path(os.getenv("PRAMANA_DATA_DIR", PROJECT_ROOT / "data")).resolve()
ARTIFACTS_DIR = Path(os.getenv("PRAMANA_ARTIFACTS_DIR", PROJECT_ROOT / "artifacts")).resolve()


def config_path(name: str) -> Path:
    """Return a YAML config path and guarantee it remains inside ``configs/``."""
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ValueError("Config name must be a single file name")
    filename = name if name.endswith((".yaml", ".yml")) else f"{name}.yaml"
    return CONFIG_DIR / filename
