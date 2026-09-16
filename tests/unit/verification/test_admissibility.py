"""Admissibility screen tests (SCOPE.md 2 component 0).

Two failure modes matter here and they pull in opposite directions:

  * letting through a claim a permutation test cannot support ("always", "causes"),
    which would attach a proof object to a sentence that claims more than the proof;
  * refusing ordinary hedged claims, which would make the gateway useless -- a screen
    that refuses everything is trivially sound and worthless.

The false-positive tests below are as important as the true-positive ones.
"""

from __future__ import annotations

import pytest

from pramana.contracts.enums import ClaimType, Direction
from pramana.verification.admissibility import ADMISSIBLE, AdmissibilityResult, screen
from tests.fixtures.candidates import candidate
from tests.fixtures.frames import toy_frame

COLUMNS = list(toy_frame(n_rows=20).columns)


def _claim(text: str, claim_type: ClaimType = ClaimType.CORRELATION, variables=None):
    return candidate(
        "c-1", text, claim_type, variables or ["age", "bmi"], direction=Direction.POSITIVE
    )


# --- claims that must be refused ------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "bmi is always higher when age is higher",
        "age and bmi never move together",
        "all patients with higher age have higher bmi",
        "every increase in age raises bmi",
        "higher age guarantees higher bmi",
        "no one with high age has low bmi",
    ],
)
def test_universal_wording_is_refused(text: str) -> None:
    """A permutation test compares an observed statistic against a shuffled null.
    That can support a tendency. It cannot support a universal.
    """
    result = screen(_claim(text), COLUMNS)
    assert not result.admissible
    assert "universal wording" in (result.reason or "")


@pytest.mark.parametrize(
    "text",
    [
        "age causes bmi to rise",
        "higher age leads to higher bmi",
        "age makes bmi increase",
        "higher bmi results in higher age",
        "bmi is higher because of age",
    ],
)
def test_causal_wording_is_refused(text: str) -> None:
    """The data is observational. No p-value licenses a causal verb."""
    result = screen(_claim(text), COLUMNS)
    assert not result.admissible
    assert "causal wording" in (result.reason or "")


def test_distribution_claims_are_refused_rather_than_approximated() -> None:
    """There is no template for `distribution`, and fail-closed means refusing --
    not substituting a generic test that answers a different question.
    """
    result = screen(_claim("income is right-skewed", ClaimType.DISTRIBUTION), COLUMNS)
    assert not result.admissible
    assert "no falsification template" in (result.reason or "")


def test_missing_column_is_refused_before_the_executor_sees_it() -> None:
    result = screen(_claim("x", variables=["age", "cholesterol"]), COLUMNS)
    assert not result.admissible
    assert "cholesterol" in (result.reason or "")


@pytest.mark.parametrize("variables", [["age"], ["age", "bmi", "income"]])
def test_wrong_number_of_variables_is_refused(variables: list[str]) -> None:
    result = screen(_claim("x", variables=variables), COLUMNS)
    assert not result.admissible
    assert "exactly 2 columns" in (result.reason or "")


# --- claims that must NOT be refused --------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "bmi is associated with age",
        "bmi tends to be higher when age is higher",
        "income tends to be higher in urban areas",
        "there is a small positive association between age and bmi",
        "generally, older respondents report higher bmi",
    ],
)
def test_hedged_claims_are_admitted(text: str) -> None:
    assert screen(_claim(text), COLUMNS) == ADMISSIBLE


@pytest.mark.parametrize(
    "text",
    [
        "smaller values of age track smaller bmi",          # 'small' contains 'all'
        "nonetheless bmi is associated with age",           # 'nonetheless' contains 'none'
        "the overall pattern is a positive association",    # 'overall' contains 'all'
        "callers report higher bmi with age",               # 'callers' contains 'all'
    ],
)
def test_word_boundaries_prevent_false_refusals(text: str) -> None:
    """`all` inside `small` must not trip the screen. Substring matching here would
    quietly refuse a large fraction of ordinary English.
    """
    assert screen(_claim(text), COLUMNS).admissible


def test_screen_ignores_the_data_entirely() -> None:
    """The decision must not depend on values, or it becomes a decision made after
    peeking at the result it would have produced.
    """
    claim = _claim("bmi is associated with age")
    assert screen(claim, COLUMNS) == screen(claim, list(reversed(COLUMNS)))


def test_first_failure_wins_deterministically() -> None:
    """A claim that breaks several rules always reports the same one, so the reason
    handed back to the agent is stable across runs.
    """
    claim = _claim("age always causes cholesterol", variables=["age", "cholesterol"])
    reasons = {screen(claim, COLUMNS).reason for _ in range(5)}
    assert len(reasons) == 1
    assert "universal wording" in reasons.pop()


# --- the result model itself ----------------------------------------------


def test_refusal_without_a_reason_is_impossible() -> None:
    with pytest.raises(ValueError, match="non-empty reason"):
        AdmissibilityResult(admissible=False)


def test_admission_with_a_reason_is_impossible() -> None:
    with pytest.raises(ValueError, match="must not carry a refusal reason"):
        AdmissibilityResult(admissible=True, reason="why would this be set")
