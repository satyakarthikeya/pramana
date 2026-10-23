"""Well-known survey variable names, so the Data Reader can say what a column holds.

Only variables whose meaning is public and stable are listed (NHANES naming). A match is
a hint that the column follows that convention, never a fact about the file: the reader
tells the user to confirm it against the cycle's documentation.
"""

from __future__ import annotations

from typing import NamedTuple

#: NHANES conventions: for coded questions 7 / 77 / 777 mean "Refused" and 9 / 99 / 999
#: mean "Don't know". They are labels, not measurements.
REFUSED_DONT_KNOW: dict[str, str] = {"7": "Refused", "9": "Don't know"}


class Variable(NamedTuple):
    label: str
    unit: str | None = None
    coding: dict[str, str] | None = None


NHANES: dict[str, Variable] = {
    "SEQN": Variable("Respondent sequence number (identifier)"),
    "RIDAGEYR": Variable("Age at screening", "years"),
    "RIAGENDR": Variable("Sex", None, {"1": "Male", "2": "Female"}),
    "RIDRETH1": Variable(
        "Race and Hispanic origin",
        None,
        {
            "1": "Mexican American",
            "2": "Other Hispanic",
            "3": "Non-Hispanic White",
            "4": "Non-Hispanic Black",
            "5": "Other race, including multiracial",
        },
    ),
    "DMDEDUC2": Variable(
        "Education level, adults 20 and over",
        None,
        {
            "1": "Less than 9th grade",
            "2": "9th to 11th grade",
            "3": "High school graduate or GED",
            "4": "Some college or associate degree",
            "5": "College graduate or above",
            "7": "Refused",
            "9": "Don't know",
        },
    ),
    "INDFMPIR": Variable("Ratio of family income to the poverty level"),
    "BMXBMI": Variable("Body mass index", "kg/m^2"),
    "BMXWT": Variable("Body weight", "kg"),
    "BMXHT": Variable("Standing height", "cm"),
    "BMXWAIST": Variable("Waist circumference", "cm"),
    "BPXSY1": Variable("Systolic blood pressure, first reading", "mm Hg"),
    "BPXDI1": Variable("Diastolic blood pressure, first reading", "mm Hg"),
    "LBXGLU": Variable("Fasting plasma glucose", "mg/dL"),
    "LBXGH": Variable("Glycohemoglobin (HbA1c)", "%"),
    "LBXTC": Variable("Total cholesterol", "mg/dL"),
    "LBDHDD": Variable("Direct HDL cholesterol", "mg/dL"),
    "LBDLDL": Variable("LDL cholesterol", "mg/dL"),
    "SMQ020": Variable(
        "Smoked at least 100 cigarettes in life",
        None,
        {"1": "Yes", "2": "No", "7": "Refused", "9": "Don't know"},
    ),
}


def lookup(column: str) -> Variable | None:
    """The NHANES variable for a column name (case-insensitive), or None."""
    return NHANES.get(column.strip().upper())
