"""Shared enums for the inter-module contracts (PROJECT.md 5).

Every member is a `StrEnum`, so a value survives a YAML/JSON round trip as the plain
lowercase string it was written as, and code that interpolates one into generated
source or a log line gets the value rather than `ClaimType.CORRELATION`.

Two of these enums are wider than PROJECT.md 5 described, and deliberately so:

  * `GateOutcome` records WHY a verdict came out the way it did. `Verdict` alone
    cannot distinguish "the data refutes this claim" from "we could not test it",
    and the analysis agent needs that distinction to decide whether to rewrite a
    claim or drop it. `Verdict` stays two-valued because it is what the memory guard
    checks (AGENTS.md 0) -- one boolean gate, many reasons behind it.
  * `EffectMetric` names the metric the gate THRESHOLDS on. Metrics that are merely
    reported for human readers (Hedges' g, Theil-Sen slope, Pearson r) are not
    members: they carry no threshold, so nothing may gate on them.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md
"""

from __future__ import annotations

from enum import StrEnum


class ClaimType(StrEnum):
    """The shape of the relationship a candidate insight asserts (PROJECT.md 5).

    `DISTRIBUTION` is a valid contract value with NO falsification template, so every
    distribution claim is screened out as `NOT_TESTABLE` before any code is generated.
    That is DELIBERATE, not an unfinished branch: the rule is fail-closed, and
    substituting a generic test for a claim shape nobody designed a null for would
    produce a p-value that does not answer the sentence it is attached to
    (`admissibility.py`, `TESTABLE_CLAIM_TYPES`). It stays in the enum because the
    analysis module legitimately produces such claims and needs a way to say so.
    """

    CORRELATION = "correlation"
    GROUP_DIFFERENCE = "group_difference"
    TREND = "trend"
    DISTRIBUTION = "distribution"


class Verdict(StrEnum):
    """The gate's binary decision. `PASS` is the ONLY value that opens memory."""

    PASS = "PASS"
    REJECT = "REJECT"


class TestType(StrEnum):
    """Which vetted procedure produced the p-value."""

    PERMUTATION = "permutation"
    BOOTSTRAP = "bootstrap"


class Direction(StrEnum):
    """The sign of a relationship, asserted by a claim or observed in the data."""

    POSITIVE = "positive"
    NEGATIVE = "negative"


class EffectMetric(StrEnum):
    """Effect-size metrics the gate thresholds on.

    Each member MUST have a band in `configs/verification.yaml`; the config tests
    enforce that, because a missing band would surface as a `KeyError` at verdict
    time rather than at load time.
    """

    SPEARMAN_RHO = "spearman_rho"
    KENDALL_TAU_B = "kendall_tau_b"
    CLIFFS_DELTA = "cliffs_delta"
    EPSILON_SQUARED = "epsilon_squared"
    CRAMERS_V = "cramers_v"


class GateOutcome(StrEnum):
    """Why the gate decided what it decided.

    `SUPPORTED` is the single outcome that maps to `Verdict.PASS`; `ProofObject`
    refuses any other pairing, which is AGENTS.md 0 expressed as a type rather than
    as a convention.

    * `SUPPORTED`     -- survived falsification: q < alpha, effect clears its band,
                         and the observed direction matches any asserted one.
    * `REFUTED`       -- significant, but the effect points the other way.
    * `NEGLIGIBLE`    -- significant, but the effect is too small to be a finding.
    * `INCONCLUSIVE`  -- not significant after BH, OR the test failed to produce a
                         usable result (crash, timeout, malformed output). Both are
                         "we learned nothing", and both fail closed.
    * `NOT_TESTABLE`  -- refused by the admissibility screen before any code ran, so
                         no statistics exist for it and it is not in the BH family.
    """

    SUPPORTED = "supported"
    REFUTED = "refuted"
    NEGLIGIBLE = "negligible"
    INCONCLUSIVE = "inconclusive"
    NOT_TESTABLE = "not_testable"
