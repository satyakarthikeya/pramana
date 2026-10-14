"""Prompt templates for the LLM falsification generator, one per claim type.

What the model is and is not asked to do
---------------------------------------
The model writes CODE. It never reports a statistic, a p-value, or a verdict. That
separation is the whole reason an LLM is allowed near the gate at all (AGENTS.md 3.1):
a number a model asserts is an opinion, and a number that falls out of executing
audited code is evidence. So every prompt here asks for one thing -- a module that
calls `pramana.verification.stats` -- and the prompts state plainly that any p-value
written as a literal will be rejected.

Null-hypothesis framing
-----------------------
Each prompt names the null explicitly and asks for code that tries to DISPROVE the
claim. This is not decoration. A prompt phrased as "test whether X relates to Y"
invites code that looks for the relationship; a prompt phrased as "the null is that X
and Y are unrelated; destroy the association and see whether the observed value is
remarkable against that" describes a permutation test. The wording steers the model
toward the procedure we can actually verify.

Why the constants are dictated rather than left to the model
------------------------------------------------------------
`N_PERMUTATIONS`, `SEED` and `MIN_OBSERVATIONS` are given as exact literals the model
must reproduce. The executor independently refuses a payload whose resample count or
seed disagrees with the run's config, so a model that ignores the instruction fails
closed one layer later. Dictating them here turns that late, expensive failure into an
early, cheap one -- and keeps the reproducibility promise (AGENTS.md 3.4) a property
of the config rather than of the model's cooperation.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 6
"""

from __future__ import annotations

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType
from pramana.verification.executor import runner

#: The claim types the LLM generator will write code for. Deliberately identical to
#: `templates.SUPPORTED_CLAIM_TYPES`: the LLM path is measured against the template
#: path, and a generator that covered a different set of claims would not be a
#: comparison. `DISTRIBUTION` is absent from both, and the admissibility screen
#: refuses it earlier.
SUPPORTED_CLAIM_TYPES = frozenset(
    {ClaimType.CORRELATION, ClaimType.GROUP_DIFFERENCE, ClaimType.TREND}
)

#: Stated once, applied to every claim type. The rules are phrased as hard refusals
#: rather than preferences because the generated module is checked against each of
#: them mechanically afterwards, and a model that treats them as suggestions produces
#: code the policy rejects.
SYSTEM_PROMPT = """\
You write Python falsification tests for a statistical verification gateway.

Your output is executed inside a sandbox. It is not read by a human and it is not \
trusted. Follow these rules exactly.

WHAT YOU PRODUCE
- One complete Python module, and nothing else.
- It defines exactly one function: `def falsify(frame):` taking a pandas DataFrame \
and returning a dict.
- No `print`, no file access, no network, no `__main__` block, no example usage.

WHAT YOU MAY IMPORT
- `numpy`, `pandas`, and `pramana.verification.stats`. Nothing else.
- Importing `scipy`, `statsmodels`, `sklearn`, or any other statistics library is \
refused by the sandbox and your output is discarded.
- Never import or reference `provenance`, and never touch any name starting with an \
underscore from the stats package.

WHICH DATA YOU MAY READ
- Read ONLY the two columns named in VAR_X and VAR_Y, selected first and by name, for \
example `frame[[VAR_X, VAR_Y]]`. Write column names as string literals or as the \
module-level constants; a name built at runtime is refused.
- Never alias, copy or pass the whole frame anywhere, and never read another column.
- Do not filter rows. No boolean masks, `.query`, `.head`, `.sample`, `.iloc` or \
slicing. The only permitted exclusion is dropping rows with missing values in those two \
columns. The one exception is a group_difference claim, which may select the rows of one \
level of VAR_X with `==`.

WHERE THE NUMBERS COME FROM
- You MUST obtain the p-value by calling `permutation_test` or \
`permutation_test_groups` from `pramana.verification.stats`.
- You MUST NOT compute a p-value yourself, and you MUST NOT write any statistic as a \
literal. A hardcoded p-value is the failure mode this entire system exists to catch.
- Copy `result.provenance`, `result.seed` and `result.n_permutations` into the \
returned dict unchanged. They are what prove the number came from the audited code.

HOW YOU ANSWER
- Return only the module source, in a single ```python fenced block.
- No commentary before or after the block.\
"""

#: The null each claim type is tested against, and the procedure that destroys it.
#: Phrased per type because "shuffle it and look" means something different for a
#: paired correlation than for group labels.
_NULL_FRAMING: dict[ClaimType, str] = {
    ClaimType.CORRELATION: (
        "NULL HYPOTHESIS: {var_x} and {var_y} are unrelated, and the observed rank "
        "correlation is an accident of this sample.\n"
        "HOW TO DESTROY IT: shuffle {var_y} against {var_x}. That removes any "
        "association while leaving both marginal distributions untouched, which is "
        "exactly the null. Use `spearman_rho` as the statistic passed to "
        "`permutation_test`."
    ),
    ClaimType.TREND: (
        "NULL HYPOTHESIS: {var_y} has no monotonic relationship with {var_x}.\n"
        "HOW TO DESTROY IT: shuffle {var_y} against {var_x} and compare the observed "
        "rank concordance against the shuffles. Use `kendall_tau_b` as the statistic "
        "passed to `permutation_test`, because a trend claim is about monotonicity "
        "and tau asks that without assuming the shape of the relationship."
    ),
    ClaimType.GROUP_DIFFERENCE: (
        "NULL HYPOTHESIS: the levels of {var_x} carry no information about {var_y}.\n"
        "HOW TO DESTROY IT: reshuffle group membership with `permutation_test_groups`, "
        "preserving group SIZES and moving only the labels. For exactly two groups use "
        "`cliffs_delta` as the statistic; for more than two use `epsilon_squared`, "
        "which is unsigned because 'these groups differ' has no direction."
    ),
}

#: What each key of the returned dict is. The set of keys the prompt DEMANDS is not
#: written here: it is `executor.runner.REQUIRED_KEYS`, read at build time, so the prompt
#: and the executor cannot drift apart again (they did once: `reported_effect` was
#: required by the executor and missing from the prompt, so every LLM-written program
#: was refused). This table only supplies the wording, in the order they are listed.
#: A required key with no entry here makes `build_prompt` raise, so adding a key to the
#: executor without telling the model is a loud failure, not a silent refusal rate.
_KEY_DESCRIPTIONS: dict[str, str] = {
    "p_value": "result.p_value, unmodified",
    "effect_size": "result.statistic, unmodified",
    "effect_metric": "the string {metric!r}",
    "reported_effect": "{reported}",
    "reported_effect_metric": "the string {reported_metric!r}",
    "n_observations": "int, the usable row count after dropping missing values",
    "seed": "result.seed, unmodified",
    "n_permutations": "result.n_permutations, unmodified",
    "statistic": "result.statistic, unmodified",
    "provenance": "result.provenance, unmodified",
}

#: Keys the gateway reads from the payload but the executor does not insist on. They are
#: requested anyway: `reported_effect_metric` labels `reported_effect` in the proof
#: object, and a number without its unit is not a reportable effect.
_REQUESTED_BUT_NOT_REQUIRED: frozenset[str] = frozenset(
    {"reported_effect_metric", "n_observations"}
)

#: The second, reader-facing effect each claim type reports, and the vetted function
#: that computes it. It is a description of a CALL, never a number: the model does not
#: get to supply a statistic.
_REPORTED_EFFECT: dict[ClaimType, tuple[str, str]] = {
    ClaimType.CORRELATION: ("pearson_r(x, y), called on the same two arrays", "pearson_r"),
    ClaimType.TREND: ("sens_slope(x, y), called on the same two arrays", "sens_slope"),
    ClaimType.GROUP_DIFFERENCE: (
        "hedges_g(group_a, group_b) for exactly two groups, or eta_squared(groups) "
        "for more than two, called on the same groups the test used",
        "hedges_g' for two groups or 'eta_squared",
    ),
}


def _return_contract(claim_type: ClaimType, metric: str) -> str:
    """The returned-dict contract, derived from the executor's `REQUIRED_KEYS`.

    Guarantees: every key in `REQUIRED_KEYS` appears, quoted, with a description, and a
    key the executor requires but this module cannot describe raises `ValueError`. The
    set is read from the runner module at call time (not import time) so a change to the
    executor reaches the prompt without a second edit.
    """
    required = set(runner.REQUIRED_KEYS)
    wanted = required | _REQUESTED_BUT_NOT_REQUIRED
    undocumented = sorted(required - _KEY_DESCRIPTIONS.keys())
    if undocumented:
        raise ValueError(
            f"executor requires keys {undocumented} that the prompt contract has no "
            f"wording for; add them to _KEY_DESCRIPTIONS so the model is told to return "
            f"them (otherwise every generated program is refused)"
        )
    reported, reported_metric = _REPORTED_EFFECT[claim_type]
    lines = [
        f'  "{key}"'.ljust(26) + "-- " + _KEY_DESCRIPTIONS[key].format(
            metric=metric, reported=reported, reported_metric=reported_metric
        )
        for key in _KEY_DESCRIPTIONS
        if key in wanted
    ]
    return (
        "The returned dict must contain exactly these keys:\n"
        + "\n".join(lines)
        + '\n\n"effect_size" and "statistic" must be the SAME value. The verifier '
        "rejects a payload where they differ."
    )


#: Which gating metric each claim type reports. Two-group versus k-group is decided
#: inside the generated code, so group_difference carries both.
_METRIC_FOR: dict[ClaimType, str] = {
    ClaimType.CORRELATION: "spearman_rho",
    ClaimType.TREND: "kendall_tau_b",
    ClaimType.GROUP_DIFFERENCE: "cliffs_delta' for two groups or 'epsilon_squared",
}


def build_prompt(
    candidate: CandidateInsight,
    *,
    var_x: str,
    var_y: str,
    n_permutations: int,
    seed: int,
    min_observations: int,
) -> tuple[str, str]:
    """Build the (system, user) pair that asks for one falsification module.

    Guarantees: the same arguments always produce the same pair, so a generation that
    is replayed with the same config and candidate sends the same request. Raises for
    a claim type with no framing rather than sending a vague prompt and hoping -- the
    gateway fails closed on an untestable claim, it does not improvise a test.
    """
    if candidate.claim_type not in _NULL_FRAMING:
        raise ValueError(
            f"no falsification prompt for claim_type {candidate.claim_type!r}; the "
            f"gateway fails closed rather than asking for a generic test "
            f"(SCOPE.md 4 step 8)"
        )

    framing = _NULL_FRAMING[candidate.claim_type].format(var_x=var_x, var_y=var_y)
    contract = _return_contract(candidate.claim_type, _METRIC_FOR[candidate.claim_type])

    direction = (
        f"The claim asserts a {candidate.asserted_direction.value} direction. Do NOT "
        f"use that to pick a one-sided test: always pass alternative=\"two-sided\". "
        f"The direction is checked separately, and a one-sided test would count the "
        f"same assumption twice."
        if candidate.asserted_direction is not None
        else "The claim asserts no direction. Pass alternative=\"two-sided\"."
    )

    reference = (
        f"\nThe claim is about the group {candidate.reference_group!r}. Order the "
        f"groups so that it comes first, so a positive effect means that group sits "
        f"higher.\n"
        if candidate.reference_group is not None
        else ""
    )

    user = f"""\
CLAIM ({candidate.claim_type.value}): {candidate.claim!r}

COLUMNS
  VAR_X = {var_x!r}
  VAR_Y = {var_y!r}

{framing}

{direction}
{reference}
REQUIRED CONSTANTS -- define these at module level with exactly these values:
  N_PERMUTATIONS = {n_permutations}
  SEED = {seed}
  MIN_OBSERVATIONS = {min_observations}

Pass N_PERMUTATIONS and SEED into the permutation call. If fewer than \
MIN_OBSERVATIONS usable rows remain after dropping missing values, raise a \
ValueError rather than returning a result computed from a handful of points.

Drop rows with missing values pairwise. Never impute: an invented observation inside \
a falsification test defeats its purpose.

{contract}

Write the module now."""

    return SYSTEM_PROMPT, user
