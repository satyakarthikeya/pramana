"""The Data Reader reports counted facts; planted problems must be found, clean data left alone."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.analysis import infer_schema, load_config
from pramana.analysis.codebook import lookup
from pramana.analysis.reader import DataBrief, read_data


def _brief(frame: pd.DataFrame) -> DataBrief:
    return read_data(frame, infer_schema(frame, load_config().schema_inference))


def _kinds(brief: DataBrief, column: str) -> set[str]:
    return {note.kind for c in brief.columns if c.name == column for note in c.notes}


def _column(brief: DataBrief, name: str):
    return next(c for c in brief.columns if c.name == name)


@pytest.fixture()
def nhanes_like() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    n = 400
    age = rng.integers(18, 80, n).astype(float)
    smoke = rng.choice([1.0, 2.0], n)
    smoke[:12] = 9.0  # "Don't know"
    smoke[12:15] = 7.0  # "Refused"
    bmi = rng.normal(27, 4, n)
    bmi[:8] = 999.0  # a code in a column with no stated coding
    return pd.DataFrame(
        {
            "SEQN": np.arange(n, dtype=float) + 1000,
            "RIDAGEYR": age,
            "RIAGENDR": rng.choice([1.0, 2.0], n),
            "SMQ020": smoke,
            "BMXBMI": bmi,
            "weight_kg": rng.normal(80, 10, n),
        }
    )


def test_recognised_survey_variables_get_a_label_unit_and_coding(nhanes_like: pd.DataFrame) -> None:
    brief = _brief(nhanes_like)
    age = _column(brief, "RIDAGEYR")
    assert age.label == "Age at screening" and age.unit == "years"
    assert _column(brief, "RIAGENDR").coding == {"1": "Male", "2": "Female"}
    assert brief.recognised == 5  # SEQN, RIDAGEYR, RIAGENDR, SMQ020, BMXBMI
    assert _kinds(brief, "RIDAGEYR") == set()  # context lives in the label, not a note
    assert lookup("ridageyr") is lookup("RIDAGEYR")
    assert lookup("my_column") is None


def test_stated_refused_and_dont_know_codes_are_flagged_with_counts(
    nhanes_like: pd.DataFrame,
) -> None:
    brief = _brief(nhanes_like)
    notes = [n for n in _column(brief, "SMQ020").notes if n.kind == "coded_missing"]
    by_value = {int(n.evidence["value"]): n for n in notes}
    assert set(by_value) == {7, 9}
    assert by_value[9].evidence["rows"] == 12 and by_value[7].evidence["rows"] == 3
    assert all(n.level == "check" for n in notes)
    assert "Don't know" in by_value[9].message


def test_an_unstated_top_code_is_flagged_but_ordinary_values_are_not(
    nhanes_like: pd.DataFrame,
) -> None:
    brief = _brief(nhanes_like)
    flagged = [n for n in _column(brief, "BMXBMI").notes if n.kind == "possible_missing_code"]
    assert (
        len(flagged) == 1
        and flagged[0].evidence["value"] == 999
        and flagged[0].evidence["rows"] == 8
    )
    # Ages 18-79 include 77 and 9 would be real values, not codes: nothing should fire.
    assert "possible_missing_code" not in _kinds(brief, "RIDAGEYR")
    assert "coded_missing" not in _kinds(brief, "RIDAGEYR")


def test_identifier_unit_hint_and_headline(nhanes_like: pd.DataFrame) -> None:
    brief = _brief(nhanes_like)
    assert "id_like" in _kinds(brief, "SEQN")
    assert not _column(brief, "SEQN").usable
    assert "unit_hint" in _kinds(brief, "weight_kg")
    assert brief.columns_to_check == 2  # SMQ020 and BMXBMI
    assert brief.headline.startswith("400 rows and 6 columns")
    assert "2 columns worth a closer look" in brief.headline


def test_missing_constant_outliers_skew_and_few_rows() -> None:
    rng = np.random.default_rng(5)
    n = 300
    frame = pd.DataFrame(
        {
            "mostly_empty": np.where(rng.random(n) < 0.4, np.nan, rng.normal(size=n)),
            "constant": np.ones(n),
            "with_outliers": np.concatenate([rng.normal(0, 1, n - 4), [60, -70, 90, 80]]),
            "skewed": rng.lognormal(0, 1.4, n),
            "fine": rng.normal(size=n),
        }
    )
    brief = _brief(frame)
    assert "high_missing" in _kinds(brief, "mostly_empty")
    assert _column(brief, "mostly_empty").notes[0].evidence["share_pct"] > 30
    assert "constant" in _kinds(brief, "constant")
    outliers = next(n for n in _column(brief, "with_outliers").notes if n.kind == "outliers")
    assert outliers.evidence["rows"] >= 4
    assert "skewed" in _kinds(brief, "skewed")
    assert _kinds(brief, "fine") == set()
    sparse = pd.DataFrame({"a": [1.0] * 10 + [np.nan] * 290, "b": rng.normal(size=300)})
    assert "few_rows" in _kinds(_brief(sparse), "a")


def test_two_level_codes_and_text_numbers() -> None:
    rng = np.random.default_rng(1)
    frame = pd.DataFrame(
        {
            "flag": rng.choice([0.0, 1.0], 200),
            "as_text": pd.Series(rng.integers(0, 100, 200).astype(str), dtype=object),
            "measure": rng.normal(size=200),
        }
    )
    brief = _brief(frame)
    assert "two_level_code" in _kinds(brief, "flag")
    assert "stored_as_text" in _kinds(brief, "as_text")


def test_clean_table_has_nothing_to_check_and_brief_is_json_safe() -> None:
    rng = np.random.default_rng(9)
    frame = pd.DataFrame({"a": rng.normal(size=200), "b": rng.normal(size=200)})
    brief = _brief(frame)
    assert brief.columns_to_check == 0 and "Nothing needs a closer look" in brief.headline
    assert DataBrief.model_validate_json(brief.model_dump_json()) == brief


def test_a_legitimate_top_of_range_value_is_not_called_a_missing_code() -> None:
    rng = np.random.default_rng(4)
    # Glucose-like integers 70-99: 99 is just the largest real value.
    plain = pd.DataFrame({"LBXGLU": rng.integers(70, 100, 400).astype(float)})
    assert _kinds(_brief(plain), "LBXGLU") == set()
    # A percentile column 1-99 likewise.
    pct = pd.DataFrame({"score": rng.integers(1, 100, 400).astype(float)})
    assert "possible_missing_code" not in _kinds(_brief(pct), "score")


def test_a_code_separated_by_a_real_gap_is_still_caught() -> None:
    rng = np.random.default_rng(6)
    values = rng.normal(27, 4, 400)
    values[:9] = 999.0
    brief = _brief(pd.DataFrame({"bmi_like": values}))
    flagged = [n for n in _column(brief, "bmi_like").notes if n.kind == "possible_missing_code"]
    assert len(flagged) == 1 and flagged[0].evidence["value"] == 999
