"""BH-FDR tests (SCOPE.md 4 step 3), cross-checked against statsmodels.

statsmodels is a TEST-ONLY dependency here: the production path uses our own
implementation so the correction is auditable, and the reference check proves the
two agree.
"""

from __future__ import annotations

import numpy as np
import pytest
from statsmodels.stats.multitest import multipletests

from pramana.verification.fdr import apply_bh, bh_rejections


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4, 5, 6, 7])
def test_matches_statsmodels_reference(seed: int) -> None:
    rng = np.random.default_rng(seed)
    p_values = rng.uniform(0.0001, 1.0, size=rng.integers(2, 60))
    ours = apply_bh(p_values, alpha=0.05)
    _, reference, _, _ = multipletests(p_values, alpha=0.05, method="fdr_bh")
    assert np.allclose(ours, reference, atol=1e-12)


def test_matches_reference_with_heavy_ties() -> None:
    p_values = [0.01, 0.01, 0.01, 0.5, 0.5, 1.0, 1.0, 1.0]
    ours = apply_bh(p_values, alpha=0.05)
    _, reference, _, _ = multipletests(p_values, alpha=0.05, method="fdr_bh")
    assert np.allclose(ours, reference, atol=1e-12)


def test_monotonicity_is_enforced() -> None:
    """The classic BH bug: without the cumulative-minimum step, a larger p can
    receive a smaller q, so a claim gets rejected while a stronger one does not."""
    rng = np.random.default_rng(99)
    p_values = np.sort(rng.uniform(0.0, 1.0, size=200))
    q_values = apply_bh(p_values, alpha=0.05)
    assert all(a <= b + 1e-12 for a, b in zip(q_values, q_values[1:]))  # noqa: B905


def test_q_never_below_p_and_stays_in_range() -> None:
    rng = np.random.default_rng(100)
    p_values = rng.uniform(0.0, 1.0, size=150)
    q_values = apply_bh(p_values, alpha=0.05)
    assert all(q >= p - 1e-12 for p, q in zip(p_values, q_values, strict=True))
    assert all(0.0 <= q <= 1.0 for q in q_values)


def test_order_is_preserved() -> None:
    p_values = [0.9, 0.001, 0.4, 0.02]
    q_values = apply_bh(p_values, alpha=0.05)
    assert q_values.index(min(q_values)) == 1  # the smallest p keeps its position


def test_single_hypothesis_is_uncorrected() -> None:
    assert apply_bh([0.03], alpha=0.05) == [pytest.approx(0.03)]


def test_empty_family_returns_empty() -> None:
    assert apply_bh([], alpha=0.05) == []


def test_all_ones() -> None:
    assert apply_bh([1.0, 1.0, 1.0], alpha=0.05) == [1.0, 1.0, 1.0]


def test_family_size_changes_the_verdict() -> None:
    """A claim's verdict depends on what else was tested alongside it.

    This is the property reviewers probe, so it is pinned by a test: p = 0.01
    survives in a family of 2 and does not in a family of 50.
    """
    small_family = apply_bh([0.01, 0.02], alpha=0.05)
    assert bh_rejections(small_family, alpha=0.05)[0] is True

    large_family = apply_bh([0.01] + [0.6] * 49, alpha=0.05)
    assert bh_rejections(large_family, alpha=0.05)[0] is False


def test_nan_is_refused() -> None:
    """A crashed test produces no p-value. It must never enter the family as NaN."""
    with pytest.raises(ValueError, match="NaN"):
        apply_bh([0.01, float("nan")], alpha=0.05)


@pytest.mark.parametrize("bad", [[-0.1, 0.5], [0.5, 1.5]])
def test_out_of_range_p_values_are_refused(bad: list[float]) -> None:
    with pytest.raises(ValueError):
        apply_bh(bad, alpha=0.05)


@pytest.mark.parametrize("alpha", [0.0, 1.0, -0.1, 1.5])
def test_invalid_alpha_is_refused(alpha: float) -> None:
    with pytest.raises(ValueError):
        apply_bh([0.01, 0.2], alpha=alpha)
