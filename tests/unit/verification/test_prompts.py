"""The LLM prompt contract must match what the executor demands.

The bug this file exists for: `executor/runner.py` refuses any payload missing a key in
`REQUIRED_KEYS`, while the prompt's return contract was written by hand and omitted
`reported_effect`. Every LLM-generated program that followed the prompt was therefore
refused, with a failure that looked like the model's fault. The contract is now derived
from `REQUIRED_KEYS`, and these tests make drift between the two impossible to miss.
"""

from __future__ import annotations

import pytest

from pramana.contracts.enums import ClaimType
from pramana.verification.executor import runner
from pramana.verification.falsification import prompts
from tests.fixtures.candidates import (
    TRUE_CORRELATION,
    TRUE_GROUP_DIFFERENCE,
    TRUE_TREND,
)

_BY_TYPE = {
    ClaimType.CORRELATION: TRUE_CORRELATION,
    ClaimType.TREND: TRUE_TREND,
    ClaimType.GROUP_DIFFERENCE: TRUE_GROUP_DIFFERENCE,
}


def _user_prompt(candidate) -> str:
    _, user = prompts.build_prompt(
        candidate,
        var_x=candidate.variables[0],
        var_y=candidate.variables[1],
        n_permutations=1000,
        seed=1,
        min_observations=20,
    )
    return user


@pytest.mark.parametrize("claim_type", list(_BY_TYPE))
def test_every_required_key_is_named_in_the_prompt_contract(claim_type) -> None:
    user = _user_prompt(_BY_TYPE[claim_type])
    missing = [key for key in sorted(runner.REQUIRED_KEYS) if f'"{key}"' not in user]
    assert not missing, f"prompt contract omits keys the executor requires: {missing}"


@pytest.mark.parametrize("claim_type", list(_BY_TYPE))
def test_reported_effect_and_its_metric_are_requested(claim_type) -> None:
    """`reported_effect` is required; its metric name is what the gateway records."""
    user = _user_prompt(_BY_TYPE[claim_type])
    assert '"reported_effect"' in user
    assert '"reported_effect_metric"' in user


def test_the_contract_is_derived_from_required_keys_not_copied(monkeypatch) -> None:
    """A key added to REQUIRED_KEYS without prompt text must not be silently dropped.

    Failing at prompt-build time is the point: the generator turns it into a
    NOT_TESTABLE before any model is called, instead of every program being refused
    one layer later.
    """
    monkeypatch.setattr(runner, "REQUIRED_KEYS", runner.REQUIRED_KEYS | {"brand_new_key"})
    with pytest.raises(ValueError, match="brand_new_key"):
        _user_prompt(TRUE_CORRELATION)


def test_a_documented_key_removed_from_required_keys_is_not_demanded(monkeypatch) -> None:
    monkeypatch.setattr(runner, "REQUIRED_KEYS", runner.REQUIRED_KEYS - {"provenance"})
    assert '"provenance"' not in _user_prompt(TRUE_CORRELATION).split("returned dict")[-1]


@pytest.mark.parametrize("claim_type", list(_BY_TYPE))
def test_the_prompt_names_the_reported_effect_function_for_the_claim_type(claim_type) -> None:
    expected = {
        ClaimType.CORRELATION: "pearson_r",
        ClaimType.TREND: "sens_slope",
        ClaimType.GROUP_DIFFERENCE: "hedges_g",
    }[claim_type]
    assert expected in _user_prompt(_BY_TYPE[claim_type])


def test_group_difference_prompt_shows_the_statistic_callable_signature() -> None:
    """`permutation_test_groups` calls `statistic(list_of_groups)`, one argument.

    Found by the first live DeepSeek run: told only "use `cliffs_delta`", the model
    passed the function itself, so every group-difference program died with
    `cliffs_delta() missing 1 required positional argument: 'b'` (fail-closed, but a
    100% refusal rate for the claim type).
    """
    user = _user_prompt(TRUE_GROUP_DIFFERENCE)
    assert "lambda parts: cliffs_delta(parts[0], parts[1])" in user
    assert "lambda parts: epsilon_squared(list(parts))" in user


def test_group_difference_prompt_shows_the_one_row_selection_the_column_check_accepts() -> None:
    """The second live-run finding: with the signature fixed, DeepSeek built groups with
    a boolean-mask or other row filter and `check_columns` refused all of them. The only
    accepted form is `.loc[<frame>[VAR_X] == level, VAR_Y]`; the prompt must show it.
    """
    user = _user_prompt(TRUE_GROUP_DIFFERENCE)
    assert ".loc[columns[VAR_X].astype(str) == level, VAR_Y]" in user
