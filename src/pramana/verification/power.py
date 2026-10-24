"""Detectable effect sizes, for the "how big would it have to be" note on a REJECT.

Normal-theory approximations (Fisher z for rank correlations, a two-sample normal
approximation for Cliff's delta, a noncentral F for epsilon squared). They are
descriptive and conservative in one direction only: the level used is the run's alpha
before the multiple-testing correction, so a corrected test needed a larger effect.
Nothing here decides a verdict (AGENTS.md 3.3: no threshold lives here).
"""

from __future__ import annotations

import math

from scipy import optimize, stats

from pramana.contracts import EffectMetric, PermutationScheme, PowerNote

#: Asymptotic variance inflation of Spearman's rho over Pearson's r under normality.
_SPEARMAN_INFLATION = 1.06
_MIN_N = 8


def _z(alpha: float, power: float) -> float:
    return float(stats.norm.ppf(1.0 - alpha / 2.0) + stats.norm.ppf(power))


def detectable_effect(
    metric: EffectMetric, n: int, alpha: float, power: float, *, groups: int | None = None
) -> float | None:
    """The smallest effect of `metric` found with probability `power`, or None.

    Returns None where no honest closed form exists (relative change, Cramer's V) or
    the sample is too small for the approximation to mean anything.
    """
    if n < _MIN_N:
        return None
    z = _z(alpha, power)
    if metric is EffectMetric.SPEARMAN_RHO:
        return float(math.tanh(z * math.sqrt(_SPEARMAN_INFLATION / (n - 3))))
    if metric is EffectMetric.KENDALL_TAU_B:
        r = math.tanh(z / math.sqrt(n - 3))
        return float(2.0 / math.pi * math.asin(r))
    if metric is EffectMetric.CLIFFS_DELTA:
        d = z * math.sqrt(4.0 / n)  # two groups of similar size
        return float(2.0 * stats.norm.cdf(d / math.sqrt(2.0)) - 1.0)
    if metric is EffectMetric.EPSILON_SQUARED and groups is not None and 2 <= groups < n:
        df1, df2 = groups - 1, n - groups
        critical = stats.f.ppf(1.0 - alpha, df1, df2)

        def shortfall(noncentrality: float) -> float:
            return float(stats.ncf.sf(critical, df1, df2, noncentrality)) - power

        upper = 1.0
        while shortfall(upper) < 0 and upper < 1e6:
            upper *= 2.0
        lam = optimize.brentq(shortfall, 1e-9, upper)
        return float(lam / (lam + n))
    return None


def power_note(
    metric: EffectMetric,
    scheme: PermutationScheme,
    *,
    n_observations: int,
    n_periods: int | None,
    n_entities: int | None,
    groups: int | None,
    alpha: float,
    power: float,
) -> PowerNote | None:
    """A `PowerNote` for the sample the test really had, or None when unavailable.

    The effective sample is what the null could vary over: whole entities for a cluster
    or paired null, periods for a block-differenced series, observations less the
    period means for a within-period shuffle, rows otherwise.
    """
    if scheme in (PermutationScheme.CLUSTER, PermutationScheme.PAIRED):
        unit, n = "entities", n_entities
    elif scheme is PermutationScheme.BLOCK_DIFFERENCED:
        unit, n = "periods", n_observations
    elif scheme is PermutationScheme.STRATIFIED and n_periods is not None:
        unit, n = "observations", n_observations - n_periods
    else:
        unit, n = "observations", n_observations
    if n is None:
        return None
    found = detectable_effect(metric, int(n), alpha, power, groups=groups)
    if found is None or not math.isfinite(found) or found <= 0.0:
        return None
    return PowerNote(
        effect_metric=metric,
        detectable_effect=found,
        n_effective=int(n),
        unit=unit,  # type: ignore[arg-type]
        alpha=alpha,
        target_power=power,
    )
