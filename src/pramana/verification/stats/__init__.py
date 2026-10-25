"""The vetted statistics library -- the ONE place p-values and effect sizes come from.

This package is the reason the sandbox whitelist can be as narrow as it is. Generated
falsification code may import `numpy`, `pandas` and this package, and nothing else:
every statistics library is blocked (`FORBIDDEN_SANDBOX_IMPORTS`), so generated code
cannot compute its own p-value. It must call one of these functions, and what it gets
back is HMAC-stamped so the parent can prove it did (`provenance.py`).

The flat re-export exists for that generated code: the templates emit a single
`from pramana.verification.stats import (...)` line, which keeps the generated module
readable and keeps the import policy check trivial to write.

`provenance` is deliberately NOT re-exported here, and `executor/policy.py` refuses it
by name in every form. The stamper is what turns a number into evidence; the internal
modules import it directly (`from pramana.verification.stats import provenance`), and
that binding on the package is exactly why the policy blocks the attribute as well as
the import.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 2
"""

from pramana.verification.stats.bootstrap import BootstrapResult, bootstrap_ci
from pramana.verification.stats.change import (
    latest_absolute_change,
    latest_change_test,
    period_change_test_groups,
    period_change_test_paired,
    relative_change,
    seasonal_range,
    seasonality_test,
    seasonality_test_from_periods,
)
from pramana.verification.stats.dependence import (
    correlation_test_differenced,
    default_block_length,
    lag1_autocorrelation,
    permutation_test_groups_clustered,
    permutation_test_groups_stratified,
    permutation_test_stratified,
    trend_test_differenced,
)
from pramana.verification.stats.effect_size import (
    cliffs_delta,
    cramers_v,
    epsilon_squared,
    eta_squared,
    hedges_g,
    kendall_tau_b,
    outlier_divergence,
    pearson_r,
    sens_slope,
    spearman_rho,
    table_k,
)
from pramana.verification.stats.forecast import (
    FORECAST_METHODS,
    METHOD_LABELS,
    Backtest,
    ForecastTest,
    PeriodSeries,
    detectable_reduction,
    forecast_claim_test,
    forecast_loss_test,
    origin_block_interval,
    period_series,
    relative_reduction,
    run_backtest,
    with_baseline,
)
from pramana.verification.stats.permutation import (
    PermutationResult,
    permutation_test,
    permutation_test_groups,
)

__all__ = [
    "FORECAST_METHODS",
    "METHOD_LABELS",
    "Backtest",
    "BootstrapResult",
    "ForecastTest",
    "PeriodSeries",
    "PermutationResult",
    "bootstrap_ci",
    "cliffs_delta",
    "correlation_test_differenced",
    "cramers_v",
    "default_block_length",
    "detectable_reduction",
    "epsilon_squared",
    "eta_squared",
    "forecast_claim_test",
    "forecast_loss_test",
    "hedges_g",
    "kendall_tau_b",
    "lag1_autocorrelation",
    "origin_block_interval",
    "latest_absolute_change",
    "latest_change_test",
    "outlier_divergence",
    "pearson_r",
    "permutation_test",
    "permutation_test_groups",
    "permutation_test_groups_clustered",
    "permutation_test_groups_stratified",
    "permutation_test_stratified",
    "period_change_test_groups",
    "period_change_test_paired",
    "relative_change",
    "relative_reduction",
    "run_backtest",
    "period_series",
    "seasonal_range",
    "seasonality_test",
    "seasonality_test_from_periods",
    "sens_slope",
    "spearman_rho",
    "table_k",
    "trend_test_differenced",
    "with_baseline",
]
