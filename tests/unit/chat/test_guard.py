"""Known-answer checks for the wording guard: no number without a tool result behind it."""

from __future__ import annotations

from pramana.chat.guard import forbidden_words, unsupported_numbers

OUTPUT = {
    "column": "age",
    "n": 1234,
    "mean": 41.2567,
    "missing_pct": 12.5,
    "eta_squared": 0.12,
    "groups": [{"group": "1.0", "n": 600}, {"group": "2.0", "n": 634}],
}


def check(text: str, **kwargs: object) -> list[str]:
    return unsupported_numbers(text, [OUTPUT], **kwargs)  # type: ignore[arg-type]


def test_numbers_that_appear_in_the_result_are_supported() -> None:
    assert check("There are 1,234 people with a mean age of 41.26.") == []
    assert check("The mean is about 41.3 and 12.5% are missing.") == []
    assert check("1234 rows") == []


def test_rounding_is_half_up_to_the_digits_shown() -> None:
    assert check("mean 41.2567") == []
    assert check("mean 41.26") == []
    assert check("mean 41") == []
    assert check("mean 41.25") == ["41.25"]  # 41.2567 does not round to 41.25
    assert check("mean 42") == ["42"]


def test_an_invented_number_is_reported() -> None:
    assert check("The mean is 55.3") == ["55.3"]
    assert check("The mean is 41.26 and the median is 39") == ["39"]


def test_a_fraction_may_be_shown_as_a_percentage_but_no_other_arithmetic() -> None:
    assert check("about 12% of the variation") == []  # 0.12 * 100
    assert check("the two groups total 1,234") == []
    assert check("the difference is 34") == ["34"]  # 634 - 600 is arithmetic: refused


def test_the_number_of_items_returned_counts_as_returned() -> None:
    assert check("there are 2 groups") == []
    assert check("there are 3 groups") == ["3"]


def test_numbers_inside_column_names_are_not_numbers() -> None:
    assert check("compare q1_score with age in 2019_wave", names=["q1_score", "2019_wave"]) == []
    assert check("compare q1_score", names=[]) == []  # 'q1' is preceded by a letter: still a name


def test_a_number_the_user_wrote_may_be_echoed() -> None:
    assert check("You asked about 65 year olds.", question="what about 65 year olds") == []
    assert check("You asked about 65 year olds.", question="what about old people") == ["65"]


def test_group_labels_that_look_like_numbers_are_supported() -> None:
    assert check("Group 2.0 has 634 people.") == []


def test_negative_numbers_and_signs() -> None:
    out = [{"rho": -0.31}]
    assert unsupported_numbers("rho is -0.31", out) == []
    assert unsupported_numbers("rho is 0.31", out) == ["0.31"]


def test_verdict_and_causal_words_are_found() -> None:
    assert forbidden_words("This is statistically significant, p = 0.01") != []
    assert forbidden_words("Age causes higher glucose") == ["causes"]
    assert forbidden_words("This finding was verified") == ["verified"]
    assert forbidden_words("It was rejected") == ["rejected"]
    assert forbidden_words("because of age") == ["because of"]
    assert forbidden_words("q = 0.01") != []
    assert forbidden_words("p = 0.01") != []
    assert forbidden_words("p<0.05") != []


def test_plain_descriptive_wording_is_allowed() -> None:
    text = "The average age is higher in group 2 than in group 1, and 12 values are missing."
    assert forbidden_words(text) == []
    assert forbidden_words("Age is associated with glucose in this table.") == []
