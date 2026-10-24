"""Deterministic falsification templates -- one per claim type, no LLM involved.

This is the REFERENCE generator and the explicit offline mode (PROJECT.md 3): no API
key, no network, no model. The shipped default is the LLM generator (D1), which sits
behind the same interface and is measured against these.

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

from pramana.contracts.enums import ClaimType, PermutationScheme

#: Shared preamble. `frame` arrives as an argument; nothing here reaches outside it.
_PREAMBLE = '''"""Falsification test for {insight_id}: {claim!r}

Null hypothesis: {null_hypothesis}
Generated deterministically from the {claim_type} template -- no model wrote this.
"""

import numpy as np
import pandas as pd

from pramana.verification.stats import (
    cliffs_delta,
    correlation_test_differenced,
    epsilon_squared,
    eta_squared,
    hedges_g,
    kendall_tau_b,
    outlier_divergence,
    pearson_r,
    permutation_test,
    permutation_test_groups,
    permutation_test_groups_clustered,
    permutation_test_groups_stratified,
    permutation_test_stratified,
    latest_absolute_change,
    latest_change_test,
    seasonal_range,
    seasonality_test_from_periods,
    sens_slope,
    spearman_rho,
    trend_test_differenced,
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
        "scheme": result.scheme.value,
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
        "scheme": result.scheme.value,
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
    columns = frame[[VAR_X, VAR_Y{structure_columns}]].copy()
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

{group_call}
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
        "scheme": result.scheme.value,
        "provenance": result.provenance,
    }
'''

_GROUP_CALL_FREE = '''    result = permutation_test_groups(
        groups, statistic,
        n_permutations=N_PERMUTATIONS, seed=SEED, alternative="two-sided",
    )'''

#: Labels move only within one period, so a group common in a high period gains nothing.
_GROUP_CALL_STRATIFIED = '''    result = permutation_test_groups_stratified(
        columns[VAR_Y].to_numpy(dtype=float), columns[VAR_X].astype(str).to_numpy(),
        columns[PERIOD].to_numpy(), statistic, order=labels,
        n_permutations=N_PERMUTATIONS, seed=SEED, alternative="two-sided",
    )'''

#: Labels move between whole entities, never between the rows of one entity.
_GROUP_CALL_CLUSTER = '''    result = permutation_test_groups_clustered(
        columns[VAR_Y].to_numpy(dtype=float), columns[VAR_X].astype(str).to_numpy(),
        columns[ENTITY].astype(str).to_numpy(), statistic, order=labels,
        n_permutations=N_PERMUTATIONS, seed=SEED, alternative="two-sided",
    )'''

_PERIOD_SERIES_HELPER = '''

def _period_series(columns):
    """The selected columns averaged per period, in period order: one value per period.

    A one-row-per-period table is unchanged by this; a panel or a ledger becomes the
    series of its period means, which is what an ordered test can run on.
    """
    columns = columns.apply(pd.to_numeric, errors="coerce").dropna()
    series = columns.groupby(PERIOD).mean().sort_index()
    if len(series) < MIN_PERIODS:
        raise ValueError(
            f"{len(series)} periods is below the configured minimum of {MIN_PERIODS}; "
            f"nothing can be concluded"
        )
    return series
'''

_TREND_DIFFERENCED_BODY = '''

def falsify(frame):
    """Try to disprove the trend without mistaking a random walk for one.

    The series is the period means of VAR_Y. The null keeps the size and short-range
    dependence of every step but not its sign: steps are sign-flipped in blocks and
    re-integrated, so only a real drift stands out.
    """
    series = _period_series(frame[[PERIOD, VAR_Y]])
    order = series.index.to_numpy(dtype=float)
    values = series[VAR_Y].to_numpy(dtype=float)
    result = trend_test_differenced(
        order, values, block_length=BLOCK_LENGTH,
        n_permutations=N_PERMUTATIONS, seed=SEED, alternative="two-sided",
    )
    return {
        "p_value": result.p_value,
        "effect_size": result.statistic,
        "effect_metric": "kendall_tau_b",
        "reported_effect": sens_slope(np.arange(values.size, dtype=float), values),
        "reported_effect_metric": "sens_slope_per_period",
        "n_observations": int(values.size),
        "seed": result.seed,
        "n_permutations": result.n_permutations,
        "statistic": result.statistic,
        "scheme": result.scheme.value,
        "provenance": result.provenance,
    }
'''

_CORRELATION_DIFFERENCED_BODY = '''

def falsify(frame):
    """Try to disprove that the two series move together, change for change.

    Both series are first-differenced, so two columns that merely drift over time do not
    count; the null moves the changes of VAR_Y in blocks against those of VAR_X.
    """
    series = _period_series(frame[[PERIOD, VAR_X, VAR_Y]])
    order = series.index.to_numpy(dtype=float)
    x = series[VAR_X].to_numpy(dtype=float)
    y = series[VAR_Y].to_numpy(dtype=float)
    result = correlation_test_differenced(
        order, x, y, block_length=BLOCK_LENGTH,
        n_permutations=N_PERMUTATIONS, seed=SEED, alternative="two-sided",
    )
    return {
        "p_value": result.p_value,
        "effect_size": result.statistic,
        "effect_metric": "spearman_rho",
        "reported_effect": pearson_r(np.diff(x), np.diff(y)),
        "reported_effect_metric": "pearson_r_of_changes",
        "n_observations": int(x.size),
        "seed": result.seed,
        "n_permutations": result.n_permutations,
        "statistic": result.statistic,
        "scheme": result.scheme.value,
        "provenance": result.provenance,
    }
'''

_CORRELATION_STRATIFIED_BODY = '''

def falsify(frame):
    """Try to disprove the association within periods.

    Values of VAR_Y are shuffled only among rows of the same period, so two columns
    that both rise over time do not count as related.
    """
    rows = frame[[VAR_X, VAR_Y, PERIOD]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(rows) < MIN_OBSERVATIONS:
        raise ValueError(
            f"{len(rows)} usable rows for ({VAR_X}, {VAR_Y}) is below the configured "
            f"minimum of {MIN_OBSERVATIONS}; nothing can be concluded"
        )
    x = rows[VAR_X].to_numpy(dtype=float)
    y = rows[VAR_Y].to_numpy(dtype=float)
    result = permutation_test_stratified(
        x, y, rows[PERIOD].to_numpy(), spearman_rho,
        n_permutations=N_PERMUTATIONS, seed=SEED, alternative="two-sided",
    )
    return {
        "p_value": result.p_value,
        "effect_size": result.statistic,
        "effect_metric": "spearman_rho",
        "reported_effect": pearson_r(x, y),
        "reported_effect_metric": "pearson_r",
        "n_observations": int(x.size),
        "seed": result.seed,
        "n_permutations": result.n_permutations,
        "statistic": result.statistic,
        "scheme": result.scheme.value,
        "provenance": result.provenance,
    }
'''

_PERIOD_CHANGE_BODY = '''

def falsify(frame):
    """Try to disprove the change from the second-latest to the latest period.

    The periods are picked inside the audited stats library; this code only hands it
    every row. With ENTITY each entity is compared with itself (its change is
    sign-flipped under the null); without, rows move between the two periods.
    """
    rows = frame[[VAR_Y, PERIOD{entity_column}]].copy()
    rows[VAR_Y] = pd.to_numeric(rows[VAR_Y], errors="coerce")
    rows = rows.dropna()
    if len(rows) < MIN_OBSERVATIONS:
        raise ValueError(
            f"{len(rows)} usable rows for {VAR_Y} is below the configured minimum of "
            f"{MIN_OBSERVATIONS}; nothing can be concluded"
        )
    values = rows[VAR_Y].to_numpy(dtype=float)
    periods = rows[PERIOD].to_numpy(dtype=float)
    result = latest_change_test(
        values, periods{entity_argument},
        n_permutations=N_PERMUTATIONS, seed=SEED, alternative="two-sided",
    )
    return {
        "p_value": result.p_value,
        "effect_size": result.statistic,
        "effect_metric": "relative_change",
        "reported_effect": latest_absolute_change(values, periods),
        "reported_effect_metric": "absolute_change",
        "n_observations": int(values.size),
        "seed": result.seed,
        "n_permutations": result.n_permutations,
        "statistic": result.statistic,
        "scheme": result.scheme.value,
        "provenance": result.provenance,
    }
'''

_SEASONALITY_BODY = '''

def falsify(frame):
    """Try to disprove a month-of-year (or quarter) pattern.

    Each year is centred on its own mean so a rise across years is not a season; the
    month labels are then shuffled only within each year.
    """
    rows = frame[[VAR_Y, PERIOD]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(rows) < MIN_OBSERVATIONS:
        raise ValueError(
            f"{len(rows)} usable rows for {VAR_Y} is below the configured minimum of "
            f"{MIN_OBSERVATIONS}; nothing can be concluded"
        )
    values = rows[VAR_Y].to_numpy(dtype=float)
    periods = rows[PERIOD].to_numpy(dtype=float)
    result = seasonality_test_from_periods(
        values, periods, cycle_length=CYCLE_LENGTH,
        n_permutations=N_PERMUTATIONS, seed=SEED,
    )
    return {
        "p_value": result.p_value,
        "effect_size": result.statistic,
        "effect_metric": "epsilon_squared",
        "reported_effect": seasonal_range(values, periods, cycle_length=CYCLE_LENGTH),
        "reported_effect_metric": "peak_to_trough_of_average_year",
        "n_observations": int(values.size),
        "seed": result.seed,
        "n_permutations": result.n_permutations,
        "statistic": result.statistic,
        "scheme": result.scheme.value,
        "provenance": result.provenance,
    }
'''

_NULL_HYPOTHESES: dict[ClaimType, str] = {
    ClaimType.CORRELATION: "{var_x} and {var_y} are unrelated; the observed rank "
    "correlation is an accident of this sample.",
    ClaimType.TREND: "{var_y} has no monotonic relationship with {var_x}.",
    ClaimType.GROUP_DIFFERENCE: "the levels of {var_x} carry no information about {var_y}.",
    ClaimType.PERIOD_CHANGE: "the latest period's {var_y} is no different from the one before.",
    ClaimType.SEASONALITY: "no month (or quarter) of the year sits apart in {var_y}.",
}

_BODIES: dict[ClaimType, str] = {
    ClaimType.CORRELATION: _NUMERIC_PAIR_HELPER + _CORRELATION_BODY,
    ClaimType.TREND: _NUMERIC_PAIR_HELPER + _TREND_BODY,
    ClaimType.GROUP_DIFFERENCE: _GROUP_DIFFERENCE_BODY,
    ClaimType.PERIOD_CHANGE: _PERIOD_CHANGE_BODY,
}

#: Bodies for the dependence-aware schemes (PLAN D6), keyed by (claim type, scheme).
#: A pair with no entry has no template: the gate refuses such a claim earlier.
_SCHEME_BODIES: dict[tuple[ClaimType, PermutationScheme], str] = {
    (ClaimType.TREND, PermutationScheme.BLOCK_DIFFERENCED): (
        _PERIOD_SERIES_HELPER + _TREND_DIFFERENCED_BODY
    ),
    (ClaimType.CORRELATION, PermutationScheme.BLOCK_DIFFERENCED): (
        _PERIOD_SERIES_HELPER + _CORRELATION_DIFFERENCED_BODY
    ),
    (ClaimType.CORRELATION, PermutationScheme.STRATIFIED): _CORRELATION_STRATIFIED_BODY,
    (ClaimType.GROUP_DIFFERENCE, PermutationScheme.STRATIFIED): _GROUP_DIFFERENCE_BODY,
    (ClaimType.GROUP_DIFFERENCE, PermutationScheme.CLUSTER): _GROUP_DIFFERENCE_BODY,
    (ClaimType.PERIOD_CHANGE, PermutationScheme.PAIRED): _PERIOD_CHANGE_BODY,
    (ClaimType.SEASONALITY, PermutationScheme.STRATIFIED): _SEASONALITY_BODY,
}

_GROUP_CALLS: dict[PermutationScheme, str] = {
    PermutationScheme.FREE: _GROUP_CALL_FREE,
    PermutationScheme.STRATIFIED: _GROUP_CALL_STRATIFIED,
    PermutationScheme.CLUSTER: _GROUP_CALL_CLUSTER,
}

#: Claim types this renderer can build. Anything else fails closed upstream, in the
#: admissibility screen -- there is deliberately no generic fallback template.
SUPPORTED_CLAIM_TYPES = frozenset(_BODIES) | {key[0] for key in _SCHEME_BODIES}


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
    scheme: PermutationScheme = PermutationScheme.FREE,
    period_column: str | None = None,
    entity_column: str | None = None,
    block_length: int | None = None,
    min_periods: int | None = None,
    cycle_length: int | None = None,
) -> str:
    """Render the falsification module for one claim.

    Guarantees: the same arguments always produce byte-identical source, so the
    `falsification_code` stored in the proof object is a complete and reproducible
    record of what ran. Raises for a claim type with no template rather than
    substituting a generic one.
    """
    if claim_type not in _BODIES and not any(k[0] is claim_type for k in _SCHEME_BODIES):
        raise ValueError(
            f"no falsification template for claim_type {claim_type!r}; the gateway "
            f"fails closed rather than substituting a generic test (SCOPE.md 4 step 8)"
        )
    if (scheme is PermutationScheme.FREE and claim_type not in _BODIES) or (
        scheme is not PermutationScheme.FREE and (claim_type, scheme) not in _SCHEME_BODIES
    ):
        raise ValueError(
            f"no falsification template for a {claim_type.value} claim under the "
            f"{scheme.value} scheme; the gateway fails closed"
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
    structural = ""
    if period_column is not None:
        structural += f"PERIOD = {period_column!r}\n"
    if entity_column is not None:
        structural += f"ENTITY = {entity_column!r}\n"
    if block_length is not None:
        structural += f"BLOCK_LENGTH = {block_length}\n"
    if min_periods is not None:
        structural += f"MIN_PERIODS = {min_periods}\n"
    if cycle_length is not None:
        structural += f"CYCLE_LENGTH = {cycle_length}\n"

    body = (
        _BODIES[claim_type]
        if scheme is PermutationScheme.FREE
        else _SCHEME_BODIES[(claim_type, scheme)]
    )
    if claim_type is ClaimType.GROUP_DIFFERENCE:
        extra = {
            PermutationScheme.STRATIFIED: ", PERIOD",
            PermutationScheme.CLUSTER: ", ENTITY",
        }.get(scheme, "")
        body = (
            body.replace("{reference_group!r}", repr(reference_group))
            .replace("{structure_columns}", extra)
            .replace("{group_call}", _GROUP_CALLS[scheme])
        )
    if claim_type is ClaimType.PERIOD_CHANGE:
        paired = entity_column is not None
        body = body.replace("{entity_column}", ", ENTITY" if paired else "").replace(
            "{entity_argument}",
            ", rows[ENTITY].astype(str).to_numpy()" if paired else "",
        )
    return header + structural + body
