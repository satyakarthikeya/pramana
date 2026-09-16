"""Deterministic falsification templates -- one per claim type, no LLM involved.

This is the DEFAULT generator (PROJECT.md 3): no API key, no network, no model. The
LLM generator sits behind the same interface and is measured against these.

What the generated code is
--------------------------
A module that defines exactly one function:

    def falsify(frame) -> dict

It receives the cleaned dataframe and returns the JSON-line payload. It does NOT read
files, print, or touch the environment -- the executor's harness does all of that.

That split is forced by the whitelist, and the reasoning is worth keeping: generated
code may import only `numpy`, `pandas` and `pramana.verification.stats`. `json` is not
on that list, so generated code physically cannot serialise its own output. Rather
than widen the whitelist to let it print, the trusted harness prints for it. Every
capability generated code does not need is a capability it does not get.

Why every template is two-sided
-------------------------------
`alternative="two-sided"` always, even when the claim asserts a direction. The gate
checks the direction separately, by comparing the observed sign against
`asserted_direction`. Running a one-sided test AND a direction check would use the
claimed direction twice -- once to halve the p-value, once to gate -- which is the
same evidence counted two ways.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 2 component 1
"""

from __future__ import annotations

from pramana.contracts.enums import ClaimType

#: Shared preamble. `frame` arrives as an argument; nothing here reaches outside it.
_PREAMBLE = '''"""Falsification test for {insight_id}: {claim!r}

Null hypothesis: {null_hypothesis}
Generated deterministically from the {claim_type} template -- no model wrote this.
"""

import numpy as np
import pandas as pd

from pramana.verification.stats import (
    cliffs_delta,
    epsilon_squared,
    eta_squared,
    hedges_g,
    kendall_tau_b,
    outlier_divergence,
    pearson_r,
    permutation_test,
    permutation_test_groups,
    sens_slope,
    spearman_rho,
)

VAR_X = {var_x!r}
VAR_Y = {var_y!r}
N_PERMUTATIONS = {n_permutations}
SEED = {seed}
MIN_OBSERVATIONS = {min_observations}
'''

_NUMERIC_PAIR_HELPER = '''

def _paired_numeric(frame):
    """Both columns as floats, with pairwise-missing rows dropped.

    Dropping pairwise rather than filling: an imputed value is an invented
    observation, and inventing data inside a falsification test is self-defeating.
    """
    pair = frame[[VAR_X, VAR_Y]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(pair) < MIN_OBSERVATIONS:
        raise ValueError(
            f"{len(pair)} usable rows for ({VAR_X}, {VAR_Y}) is below the configured "
            f"minimum of {MIN_OBSERVATIONS}; nothing can be concluded"
        )
    return pair[VAR_X].to_numpy(dtype=float), pair[VAR_Y].to_numpy(dtype=float)
'''

_CORRELATION_BODY = '''

def falsify(frame):
    """Try to disprove the claim by destroying it.

    Shuffling y against x removes any association while leaving both marginal
    distributions untouched -- that IS the null. If the observed rank correlation is
    unremarkable against ten thousand such shuffles, the claim has not survived.
    """
    x, y = _paired_numeric(frame)
    result = permutation_test(
        x, y, spearman_rho,
        n_permutations=N_PERMUTATIONS, seed=SEED, alternative="two-sided",
    )
    return {
        "p_value": result.p_value,
        "effect_size": result.statistic,
        "effect_metric": "spearman_rho",
        "reported_effect": pearson_r(x, y),
        "reported_effect_metric": "pearson_r",
        "outlier_divergence": outlier_divergence(x, y),
        "n_observations": int(x.size),
        "seed": result.seed,
        "n_permutations": result.n_permutations,
        "statistic": result.statistic,
        "provenance": result.provenance,
    }
'''

_TREND_BODY = '''

def falsify(frame):
    """Try to disprove the trend.

    Kendall's tau-b rather than a fitted slope: a trend claim is about monotonicity,
    and tau asks exactly that without assuming the shape of the relationship. The
    Theil-Sen slope rides along in original units because "+0.3 visits per month" is
    what a reader can actually use.
    """
    x, y = _paired_numeric(frame)
    result = permutation_test(
        x, y, kendall_tau_b,
        n_permutations=N_PERMUTATIONS, seed=SEED, alternative="two-sided",
    )
    return {
        "p_value": result.p_value,
        "effect_size": result.statistic,
        "effect_metric": "kendall_tau_b",
        "reported_effect": sens_slope(x, y),
        "reported_effect_metric": "sens_slope",
        "n_observations": int(x.size),
        "seed": result.seed,
        "n_permutations": result.n_permutations,
        "statistic": result.statistic,
        "provenance": result.provenance,
    }
'''

_GROUP_DIFFERENCE_BODY = '''
REFERENCE_GROUP = {reference_group!r}


def falsify(frame):
    """Try to disprove the group difference by reshuffling group membership.

    Group SIZES are preserved and only the labels move, so the null is precisely
    "which group you are in tells you nothing about the value".

    Two groups gate on Cliff's delta, which is signed. More than two gate on
    epsilon-squared, which is not -- "these groups differ" has no direction to have.
    """
    columns = frame[[VAR_X, VAR_Y]].copy()
    columns[VAR_Y] = pd.to_numeric(columns[VAR_Y], errors="coerce")
    columns = columns.dropna()
    if len(columns) < MIN_OBSERVATIONS:
        raise ValueError(
            f"{len(columns)} usable rows for ({VAR_X}, {VAR_Y}) is below the configured "
            f"minimum of {MIN_OBSERVATIONS}; nothing can be concluded"
        )

    labels = sorted(columns[VAR_X].astype(str).unique().tolist())
    if len(labels) < 2:
        raise ValueError(f"{VAR_X} has a single level; there is no difference to test")
    if REFERENCE_GROUP is not None and REFERENCE_GROUP in labels:
        # The claim names the group it is about, so put it first: a positive delta
        # then means "the reference group sits higher", which is what the claim says.
        labels = [REFERENCE_GROUP] + [name for name in labels if name != REFERENCE_GROUP]

    groups = [
        columns.loc[columns[VAR_X].astype(str) == name, VAR_Y].to_numpy(dtype=float)
        for name in labels
    ]
    if any(group.size < 2 for group in groups):
        raise ValueError(f"every level of {VAR_X} needs at least 2 observations")

    if len(groups) == 2:
        statistic = lambda parts: cliffs_delta(parts[0], parts[1])
        metric, reported, reported_metric = (
            "cliffs_delta", hedges_g(groups[0], groups[1]), "hedges_g",
        )
    else:
        statistic = lambda parts: epsilon_squared(list(parts))
        metric, reported, reported_metric = (
            "epsilon_squared", eta_squared(groups), "eta_squared",
        )

    result = permutation_test_groups(
        groups, statistic,
        n_permutations=N_PERMUTATIONS, seed=SEED, alternative="two-sided",
    )
    return {
        "p_value": result.p_value,
        "effect_size": result.statistic,
        "effect_metric": metric,
        "reported_effect": reported,
        "reported_effect_metric": reported_metric,
        "group_order": labels,
        "group_sizes": [int(group.size) for group in groups],
        "n_observations": int(sum(group.size for group in groups)),
        "seed": result.seed,
        "n_permutations": result.n_permutations,
        "statistic": result.statistic,
        "provenance": result.provenance,
    }
'''

_NULL_HYPOTHESES: dict[ClaimType, str] = {
    ClaimType.CORRELATION: "{var_x} and {var_y} are unrelated; the observed rank "
    "correlation is an accident of this sample.",
    ClaimType.TREND: "{var_y} has no monotonic relationship with {var_x}.",
    ClaimType.GROUP_DIFFERENCE: "the levels of {var_x} carry no information about {var_y}.",
}

_BODIES: dict[ClaimType, str] = {
    ClaimType.CORRELATION: _NUMERIC_PAIR_HELPER + _CORRELATION_BODY,
    ClaimType.TREND: _NUMERIC_PAIR_HELPER + _TREND_BODY,
    ClaimType.GROUP_DIFFERENCE: _GROUP_DIFFERENCE_BODY,
}

#: Claim types this renderer can build. Anything else fails closed upstream, in the
#: admissibility screen -- there is deliberately no generic fallback template.
SUPPORTED_CLAIM_TYPES = frozenset(_BODIES)


def render(
    *,
    insight_id: str,
    claim: str,
    claim_type: ClaimType,
    var_x: str,
    var_y: str,
    n_permutations: int,
    seed: int,
    min_observations: int,
    reference_group: str | None = None,
) -> str:
    """Render the falsification module for one claim.

    Guarantees: the same arguments always produce byte-identical source, so the
    `falsification_code` stored in the proof object is a complete and reproducible
    record of what ran. Raises for a claim type with no template rather than
    substituting a generic one.
    """
    if claim_type not in _BODIES:
        raise ValueError(
            f"no falsification template for claim_type {claim_type!r}; the gateway "
            f"fails closed rather than substituting a generic test (SCOPE.md 4 step 8)"
        )

    header = _PREAMBLE.format(
        insight_id=insight_id,
        claim=claim,
        claim_type=claim_type.value,
        null_hypothesis=_NULL_HYPOTHESES[claim_type].format(var_x=var_x, var_y=var_y),
        var_x=var_x,
        var_y=var_y,
        n_permutations=n_permutations,
        seed=seed,
        min_observations=min_observations,
    )
    body = _BODIES[claim_type]
    if claim_type is ClaimType.GROUP_DIFFERENCE:
        body = body.replace("{reference_group!r}", repr(reference_group))
    return header + body
