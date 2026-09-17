"""Config loader tests, and in particular the sandbox import whitelist.

`FORBIDDEN_SANDBOX_IMPORTS` is the single check standing between PRAMANA and its own
central claim. If a statistics library is importable inside generated code, that code
can compute its own p-value and the gate ends up reading a number nobody audited --
which is precisely the failure the project exists to prevent (PROJECT.md 3).

An unenforced guarantee is a comment. These tests are what make it a guarantee.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from pramana.contracts.enums import EffectMetric
from pramana.verification.config import (
    FORBIDDEN_SANDBOX_IMPORTS,
    ExecutorConfig,
    load_config,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SHIPPED_CONFIG = REPO_ROOT / "configs" / "verification.yaml"


def _valid_executor() -> dict[str, Any]:
    return {
        "timeout_seconds": 60,
        "max_memory_mb": 1024,
        "max_retries": 1,
        "allowed_imports": ["numpy", "pandas", "pramana.verification.stats"],
    }


# --- the whitelist guard --------------------------------------------------


@pytest.mark.parametrize("library", sorted(FORBIDDEN_SANDBOX_IMPORTS))
def test_statistics_library_in_whitelist_is_refused(library: str) -> None:
    """Every forbidden library is refused, not just scipy."""
    raw = _valid_executor()
    raw["allowed_imports"].append(library)
    with pytest.raises(ValidationError, match="allowed_imports must not contain"):
        ExecutorConfig.model_validate(raw)


def test_submodule_of_a_forbidden_library_is_also_refused() -> None:
    """`scipy.stats` is scipy. Matching on the root package closes the obvious dodge."""
    raw = _valid_executor()
    raw["allowed_imports"].append("scipy.stats")
    with pytest.raises(ValidationError, match="allowed_imports must not contain"):
        ExecutorConfig.model_validate(raw)


def test_clean_whitelist_loads() -> None:
    config = ExecutorConfig.model_validate(_valid_executor())
    assert config.allowed_imports == ["numpy", "pandas", "pramana.verification.stats"]


def test_vetted_stats_module_is_allowed_despite_importing_scipy() -> None:
    """The distinction the whole design rests on.

    `pramana.verification.stats` imports scipy internally. That is fine: it is our
    audited code path, reviewed and covered by known-answer tests. What must never
    happen is GENERATED code importing a statistics library directly and computing
    its own number. The whitelist draws the line between those two cases, and this
    test pins it -- a naive "reject anything that touches scipy" rule would break
    the gateway entirely.
    """
    config = ExecutorConfig.model_validate(_valid_executor())
    assert "pramana.verification.stats" in config.allowed_imports

    stats_source = (
        REPO_ROOT / "src" / "pramana" / "verification" / "stats" / "effect_size.py"
    ).read_text(encoding="utf-8")
    assert "from scipy import stats" in stats_source, (
        "premise of this test: the vetted module really does use scipy internally"
    )


def test_empty_whitelist_is_refused() -> None:
    raw = _valid_executor()
    raw["allowed_imports"] = []
    with pytest.raises(ValidationError):
        ExecutorConfig.model_validate(raw)


# --- the shipped config ---------------------------------------------------


def test_shipped_config_loads_and_forbids_statistics_libraries() -> None:
    """The config that actually runs must satisfy the guarantee, not just the schema."""
    config = load_config(SHIPPED_CONFIG)
    roots = {name.split(".")[0] for name in config.executor.allowed_imports}
    assert not (roots & FORBIDDEN_SANDBOX_IMPORTS)
    assert "pramana.verification.stats" in config.executor.allowed_imports


def test_shipped_config_defaults_to_the_deterministic_generator() -> None:
    """`template` needs no API key and no network, so the gateway runs offline."""
    assert load_config(SHIPPED_CONFIG).llm.generator == "template"


def test_p_value_floor_is_below_alpha() -> None:
    """The significance leg is undefined otherwise: it divides by log(alpha / floor)."""
    config = load_config(SHIPPED_CONFIG)
    assert 0.0 < config.p_value_floor < config.statistics.alpha


def test_every_gating_metric_has_a_threshold() -> None:
    """A missing band would raise KeyError inside the gate, at verdict time."""
    thresholds = load_config(SHIPPED_CONFIG).evidence.effect_thresholds
    assert set(thresholds) == set(EffectMetric)


# --- the loader fails loudly ----------------------------------------------


def test_missing_key_raises_at_load_time(tmp_path: Path) -> None:
    """Silent defaults are how a threshold quietly stops being the configured one."""
    raw = yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    broken = copy.deepcopy(raw)
    del broken["statistics"]["alpha"]
    target = tmp_path / "broken.yaml"
    target.write_text(yaml.safe_dump(broken), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(target)


def test_unknown_key_raises_at_load_time(tmp_path: Path) -> None:
    """`extra="forbid"`: a typo'd threshold must fail, not be ignored."""
    raw = yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    raw["statistics"]["alpha_typo"] = 0.2
    target = tmp_path / "typo.yaml"
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(target)


def test_floor_at_or_above_alpha_is_refused_at_load_time(tmp_path: Path) -> None:
    """1000 permutations floor p at ~0.001; an alpha at or below that makes the
    significance leg divide by log(1) and would raise on the first PASS. Refuse the
    combination when the config loads, not when the run is nearly over."""
    raw = yaml.safe_load(SHIPPED_CONFIG.read_text(encoding="utf-8"))
    raw["statistics"]["n_permutations"] = 1000
    raw["statistics"]["alpha"] = 0.0005
    target = tmp_path / "floor.yaml"
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValidationError, match="must be below alpha"):
        load_config(target)
