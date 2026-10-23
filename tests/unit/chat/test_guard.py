"""Known-answer checks for the wording guard: no number without a tool result behind it."""

from __future__ import annotations

from pramana.chat.guard import forbidden_words, unsupported_numbers

OUTPUT = {
    "column": "age",
    "n": 1234,
    "mean": 41.2567,
    "missing_pct": 12.5,
    "eta_squared": 0.12,
    "rho": 0.42,
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


def test_a_whole_number_is_not_accepted_for_a_small_fraction() -> None:
    assert check("rho is 0.42") == []
    assert check("rho is 0.4") == []
    assert unsupported_numbers("perfect 1", [{"rho": 0.55}]) == ["1"]  # 0.55 must not become 1
    assert unsupported_numbers("about 0", [{"rho": 0.4}]) == ["0"]


def test_an_invented_number_is_reported() -> None:
    assert check("The mean is 55.3") == ["55.3"]
    assert check("The mean is 41.26 and the median is 39") == ["39"]


def test_percentages_are_the_stored_value_or_a_fraction_times_one_hundred() -> None:
    assert check("about 12% of the variation") == []  # 0.12 * 100
    assert check("the groups total 1,234") == []
    assert check("the difference is 34") == ["34"]  # 634 - 600 is arithmetic: refused
    assert check("10000%") == ["10000%"]  # n=1234 is not a fraction, so no x100 rule
    assert unsupported_numbers("100%", [{"n": 1}]) == []  # a stored fraction of 1 is 100%
    assert unsupported_numbers("10000%", [{"n": 100}]) == ["10000%"]


def test_the_number_of_items_returned_counts_as_returned() -> None:
    assert check("there are 2 groups") == []
    assert check("there are 3 groups") == ["3"]


def test_the_users_own_numbers_are_not_trusted_as_facts() -> None:
    # A false premise must not be echoed back as if the table said it.
    assert unsupported_numbers("The mean is 999", [{"mean": 106.0}]) == ["999"]


def test_group_labels_that_look_like_numbers_are_supported() -> None:
    assert check("Group 2.0 has 634 people.") == []


def test_signs_must_match() -> None:
    out = [{"rho": -0.31}]
    assert unsupported_numbers("rho is -0.31", out) == []
    assert unsupported_numbers("rho is 0.31", out) == ["0.31"]
    # A Unicode minus is a minus: the sign cannot be flipped by a look-alike character.
    assert unsupported_numbers("rho is −0.42", [{"rho": 0.42}]) == ["-0.42"]
    assert unsupported_numbers("rho is −0.31", out) == []


def test_leading_dot_and_glued_numbers_are_still_numbers() -> None:
    assert check("rho is .75") == [".75"]
    assert check("rho is .42") == []
    assert check("p0.001") == ["0.001"]
    assert check("N999") == ["999"]
    assert check("x77 rows") == ["77"]


def test_spelled_out_numbers_and_fraction_glyphs_are_refused() -> None:
    assert check("forty people") == ["forty"]
    assert check("one hundred rows") == ["hundred"]
    assert check("about thirty") == ["thirty"]
    assert check("about ½") != []
    assert check("a ⅓ share") != []


def test_other_digit_scripts_are_read_by_value() -> None:
    assert check("１２３４ rows") == []  # fullwidth 1234
    assert check("９９９ rows") == ["999"]


def test_column_names_are_blanked_only_as_whole_tokens() -> None:
    assert check("compare q1_score with age in 2019_wave", names=["q1_score", "2019_wave"]) == []
    assert unsupported_numbers("compare q1_score", [{"n": 5}], names=[]) == ["1"]
    # A numeric or one-letter name must never switch the guard off for those digits.
    digits = [str(d) for d in range(10)]
    plain = [{"n": 5}]
    assert unsupported_numbers("8675309 rows and 42 cols", plain, names=digits) == [
        "8675309",
        "42",
    ]
    assert unsupported_numbers("1 1 1 1 11 111", plain, names=["1"]) == [
        "1", "1", "1", "1", "11", "111",
    ]  # fmt: skip
    assert unsupported_numbers("the 100", plain, names=["10"]) == ["100"]
    assert unsupported_numbers("777", plain, names=["7"]) == ["777"]


def test_verdict_and_causal_words_are_found() -> None:
    assert forbidden_words("This is statistically significant, p = 0.01") != []
    assert forbidden_words("Age causes higher glucose") == ["causes"]
    assert forbidden_words("This finding was verified") == ["verified"]
    assert forbidden_words("It was rejected") == ["rejected"]
    assert forbidden_words("because of age") != []
    assert forbidden_words("q = 0.01") != []
    assert forbidden_words("p = 0.01") != []
    assert forbidden_words("p<0.05") != []


def test_synonyms_and_disguised_spellings_do_not_slip_through() -> None:
    for text in (
        "The gateway confirmed this holds.",
        "This is proved: tested and holds.",
        "Supported by the gateway: it rises with age.",
        "It is an established, causal pattern",
        "a reliable pattern",
        "age influences glucose",
        "age determines glucose",
        "it is insignificant",
        "signifi​cant",  # zero-width character inside the word
        "sig-nificant",
        "p-val",
        "p value",
        "p  value",
        "leads  to higher glucose",
        "resulting in higher glucose",
        "verifеd",  # Cyrillic look-alike letter
    ):
        assert forbidden_words(text) != [], text


def test_plain_descriptive_wording_is_allowed() -> None:
    text = "The average age is higher in group 2 than in group 1, and 12 values are missing."
    assert forbidden_words(text) == []
    assert forbidden_words("Age is associated with glucose in this table.") == []
    assert forbidden_words("The table holds 300 rows.") == []


def test_unit_exponents_are_not_numbers_but_stray_digits_still_are() -> None:
    """A live BMI answer was withheld because of 'kg/m²'; the exponent belongs to the unit."""
    out = [{"mean": 29.096833, "missing": 0, "n": 600}]
    for text in (
        "The mean is 29.1 kg/m².",
        "The mean is 29.1 kg/m2.",
        "About 29.1 cm2 here.",
    ):
        assert unsupported_numbers(text, out) == [], text
    assert unsupported_numbers("mean 29.1, and 7 m²", out) == ["7"]
    assert unsupported_numbers("area 5 m2", out) == ["5"]
    assert unsupported_numbers("x2 rows", out) == ["2"]
    assert unsupported_numbers("the 2 groups", out) == ["2"]
