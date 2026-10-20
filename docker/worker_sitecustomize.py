"""Bound numerical thread pools before imports in every worker Python process.

The executor intentionally starts children with a minimal environment. Python loads
this image-owned startup hook again in those children, so thread limits survive
that sanitization without forwarding credentials or weakening resource limits.
"""

import os

for _variable in (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ[_variable] = "1"
