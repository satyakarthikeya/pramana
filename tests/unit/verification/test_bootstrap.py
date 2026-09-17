"""Bootstrap CI tests (SCOPE.md 4 step 2)."""

from __future__ import annotations

import numpy as np
import pytest

from pramana.verification.stats import bootstrap_ci
from pramana.verification.stats.effect_size import spearman_rho


def test_ci_covers_a_known_mean() -> None:
    rng = np.random.default_rng(1)
    sample = rng.normal(5.0, 1.0, 500)
    result = bootstrap_ci(sample, np.mean, n_bootstrap=2000, seed=3)
    assert result.ci_low < 5.0 < result.ci_high
    assert result.point_estimate == pytest.approx(float(np.mean(sample)))


def test_same_seed_reproduces_exactly() -> None:
    rng = np.random.default_rng(2)
    sample = rng.normal(size=200)
    first = bootstrap_ci(sample, np.mean, n_bootstrap=500, seed=9)
    second = bootstrap_ci(sample, np.mean, n_bootstrap=500, seed=9)
    assert (first.ci_low, first.ci_high) == (second.ci_low, second.ci_high)


def test_interval_narrows_as_n_grows() -> None:
    rng = np.random.default_rng(3)
    small = bootstrap_ci(rng.normal(size=30), np.mean, n_bootstrap=1000, seed=1)
    large = bootstrap_ci(rng.normal(size=3000), np.mean, n_bootstrap=1000, seed=1)
    assert (large.ci_high - large.ci_low) < (small.ci_high - small.ci_low)


def test_paired_resampling_preserves_the_association() -> None:
    """Resampling must be at the ROW level: breaking the pairing would destroy the
    very association being estimated and the CI would collapse toward zero."""
    rng = np.random.default_rng(4)
    x = rng.normal(size=400)
    y = 0.7 * x + rng.normal(size=400)
    result = bootstrap_ci(
        [x, y], spearman_rho, n_bootstrap=800, seed=5, paired=True
    )
    assert result.ci_low > 0.3
    assert result.excludes_zero is True


def test_null_association_interval_contains_zero() -> None:
    rng = np.random.default_rng(6)
    x, y = rng.normal(size=300), rng.normal(size=300)
    result = bootstrap_ci([x, y], spearman_rho, n_bootstrap=800, seed=7, paired=True)
    assert result.ci_low < 0.0 < result.ci_high
    assert result.excludes_zero is False


def test_confidence_level_widens_the_interval() -> None:
    rng = np.random.default_rng(8)
    sample = rng.normal(size=300)
    narrow = bootstrap_ci(sample, np.mean, n_bootstrap=1000, seed=1, confidence_level=0.80)
    wide = bootstrap_ci(sample, np.mean, n_bootstrap=1000, seed=1, confidence_level=0.99)
    assert (wide.ci_high - wide.ci_low) > (narrow.ci_high - narrow.ci_low)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"n_bootstrap": 0, "seed": 1}, "n_bootstrap"),
        ({"n_bootstrap": 10, "seed": 1, "confidence_level": 1.0}, "confidence_level"),
    ],
)
def test_invalid_parameters_are_refused(kwargs: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        bootstrap_ci(np.arange(10, dtype=float), np.mean, **kwargs)  # type: ignore[arg-type]


def test_too_few_observations_are_refused() -> None:
    with pytest.raises(ValueError, match="at least 3"):
        bootstrap_ci([1.0, 2.0], np.mean, n_bootstrap=100, seed=1)


def test_paired_columns_must_match_in_length() -> None:
    with pytest.raises(ValueError, match="equal length"):
        bootstrap_ci(
            [np.arange(10, dtype=float), np.arange(9, dtype=float)],
            spearman_rho,
            n_bootstrap=100,
            seed=1,
            paired=True,
        )
