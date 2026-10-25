"""Paraphrases resolve consistently, while overlapping meanings require clarification."""

import pytest

from pramana.chat.questions import asks_for_forecast, question_limits, resolve_columns


@pytest.mark.parametrize("question", [
    "Does age relate to systolic blood pressure?",
    "Is AGE associated with SBP?",
    "Does age_years relate to systolic_bp?",
    "Does age in years affect systolic pressure?",
    "Does this dataset prove that age causes systolic blood pressure to increase, "
    "and is it representative of the general population?",
])
def test_question_paraphrases_resolve_to_actual_columns(question: str) -> None:
    assert resolve_columns(question, {"age_years", "systolic_bp", "noise"}, None) == (
        {"age_years", "systolic_bp"}, set(),
    )


@pytest.mark.parametrize("question,expected,ambiguous", [
    ("age and blood pressure", {"age_years"}, {"systolic_bp", "diastolic_bp"}),
    ("age and systolic blood pressure", {"age_years", "systolic_bp"}, set()),
    ("age and diastolic pressure", {"age_years", "diastolic_bp"}, set()),
    ("stage and unrelated pressure", set(), set()),
])
def test_ambiguous_and_overlapping_phrases(question, expected, ambiguous) -> None:
    assert resolve_columns(question, {"age_years", "systolic_bp", "diastolic_bp"}, None) == (
        expected, ambiguous,
    )


def test_unit_variants_are_not_silently_chosen() -> None:
    assert resolve_columns("age", {"age_years", "age_yrs"}, None) == (
        set(), {"age_years", "age_yrs"},
    )


@pytest.mark.parametrize("question,columns,expected,ambiguous", [
    ("machine speed and defect rate", {"machineSpeedRPM", "defectRatePct"},
     {"machineSpeedRPM", "defectRatePct"}, set()),
    ("average ambient temperature", {"ambientTemperatureC"}, {"ambientTemperatureC"}, set()),
    ("order quantity and revenue", {"orderQuantity", "revenueUSD"},
     {"orderQuantity", "revenueUSD"}, set()),
    ("unit price", {"unitPriceUSD", "salePriceUSD"}, {"unitPriceUSD"}, set()),
    ("temperature", {"temperature_C", "temperature_F"},
     set(), {"temperature_C", "temperature_F"}),
    ("temperature in Celsius", {"temperature_C", "temperature_F"},
     {"temperature_C"}, set()),
    ("compressive strength", {"compressiveStrength(MPa)"},
     {"compressiveStrength(MPa)"}, set()),
])
def test_cross_domain_names_and_explicit_units(question, columns, expected, ambiguous) -> None:
    assert resolve_columns(question, columns, None) == (expected, ambiguous)


def test_compound_question_gets_both_limits_without_fabricating_evidence() -> None:
    notes = question_limits("Does age cause higher BP and does it generalize to everyone?")
    assert len(notes) == 2
    assert "Causation:" in notes[0] and "Population representativeness:" in notes[1]
    assert question_limits("What is the mean age?") == []


@pytest.mark.parametrize("question,columns,expected,ambiguous", [
    ("voltage and current", {"voltageV", "currentA"}, {"voltageV", "currentA"}, set()),
    ("energy in kilowatt hours and power in kilowatts", {"energy_kWh", "power_kW"},
     {"energy_kWh", "power_kW"}, set()),
    ("energy in kilowatt-hours", {"energy_kwh"}, {"energy_kwh"}, set()),
    ("current", {"current_A", "current_mA"}, set(), {"current_A", "current_mA"}),
    ("current in milliamps", {"current_A", "current_mA"}, {"current_mA"}, set()),
    ("pressure in megapascals", {"pressureMPa", "pressure_kPa"}, {"pressureMPa"}, set()),
    ("pressure in kilopascals", {"pressureMPa", "pressure_kPa"}, {"pressure_kPa"}, set()),
])
def test_physical_unit_qualifiers_resolve_without_conversion(
    question, columns, expected, ambiguous,
) -> None:
    assert resolve_columns(question, columns, None) == (expected, ambiguous)


@pytest.mark.parametrize("question", [
    "What will demand be next month?",
    "Will energy use increase next year?",
    "Next year, predict demand.",
    "Predict demand for 2027.",
    "Give a prediction of tomorrow's demand.",
    "Forecast next week's sales.",
])
def test_future_requests_do_not_depend_on_word_order(question: str) -> None:
    assert asks_for_forecast(question)


@pytest.mark.parametrize("question", [
    "What was the average forecast error last year?",
    "Summarise forecast errors in this table.",
    "Describe forecast accuracy.",
    "What is the mean forecastError?",
    "Is power associated with energy?",
    "Which columns predict demand in this table?",
])
def test_historical_forecast_metrics_are_not_requests_to_forecast(question: str) -> None:
    assert not asks_for_forecast(question)
