"""The vetted statistics library -- the ONE place p-values and effect sizes come from.

This package is the reason the sandbox whitelist can be as narrow as it is. Generated
falsification code may import `numpy`, `pandas` and this package, and nothing else:
every statistics library is blocked (`FORBIDDEN_SANDBOX_IMPORTS`), so generated code
cannot compute its own p-value. It must call one of these functions, and what it gets
back is HMAC-stamped so the parent can prove it did (`provenance.py`).

The flat re-export exists for that generated code: the templates emit a single
`from pramana.verification.stats import (...)` line, which keeps the generated module
readable and keeps the import policy check trivial to write.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 2
"""

from pramana.verification.stats.bootstrap import BootstrapResult, bootstrap_ci
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
from pramana.verification.stats.permutation import (
    PermutationResult,
    permutation_test,
    permutation_test_groups,
)

__all__ = [
    "BootstrapResult",
    "PermutationResult",
    "bootstrap_ci",
    "cliffs_delta",
    "cramers_v",
    "epsilon_squared",
    "eta_squared",
    "hedges_g",
    "kendall_tau_b",
    "outlier_divergence",
    "pearson_r",
    "permutation_test",
    "permutation_test_groups",
    "sens_slope",
    "spearman_rho",
    "table_k",
]
