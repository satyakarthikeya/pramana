"""The forecast settings in configs/verification.yaml: shipped OFF, strict, resolvable."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from pramana.contracts import EffectMetric
from pramana.verification.config import DEFAULT_CONFIG_PATH, VerificationConfig, load_config


def _raw() -> dict:
    return yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))


def test_the_shipped_default_is_off_and_the_band_exists() -> None:
    config = load_config()
    assert config.claims.forecast_enabled is False
    band = config.evidence.threshold_for(EffectMetric.MASE_REDUCTION)
    assert 0 < band.min < band.strong < 1


def test_a_config_without_the_flag_or_with_a_typo_fails_loudly() -> None:
    raw = _raw()
    del raw["claims"]
    with pytest.raises(ValidationError):
        VerificationConfig.model_validate(raw)
    raw = _raw()
    raw["claims"]["forecast_enable"] = True
    with pytest.raises(ValidationError):
        VerificationConfig.model_validate(raw)


def test_too_few_blocks_to_resolve_the_largest_family_is_refused_at_load() -> None:
    raw = _raw()
    raw["forecast"]["min_blocks"] = 5
    with pytest.raises(ValidationError, match="min_blocks"):
        VerificationConfig.model_validate(raw)


def test_the_forecast_attack_thresholds_have_no_hidden_defaults() -> None:
    raw = _raw()
    del raw["forecast"]["attacks"]["cusum_critical"]
    with pytest.raises(ValidationError):
        VerificationConfig.model_validate(raw)
