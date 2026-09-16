"""Shared test fixtures: toy dataframes with planted signals, and candidate batches.

Owner: shared (see `tests/OWNERSHIP.md`). Built by the verification module first
because the gateway needs candidates before the analysis module exists; the analysis
acceptance test is meant to consume the SAME frame, so both modules are provably
testing identical data.

Nothing here is random at call time. Every frame is built from an explicit seed, so a
failing assertion is reproducible from the test name alone.
"""

from tests.fixtures.candidates import (
    INADMISSIBLE_CANDIDATES,
    TESTABLE_CANDIDATES,
    candidate,
    demo_batch,
)
from tests.fixtures.frames import PLANTED, toy_frame

__all__ = [
    "INADMISSIBLE_CANDIDATES",
    "PLANTED",
    "TESTABLE_CANDIDATES",
    "candidate",
    "demo_batch",
    "toy_frame",
]
