"""A failed model summary still exposes useful, source-labelled computed facts."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pramana.chat.models import ChatAnswer, ChatExchange, ChatWork, Evidence
from pramana.chat.presentation import LEGACY_WITHHELD_TEXT, asks_about_dataset, computed_summary
from pramana.chat.store import ChatRepository


def stored_evidence() -> list[Evidence]:
    return [
        Evidence(
            entry_id="x1",
            tool="missingness",
            output={
                "rows": 500,
                "columns": [
                    {"column": "age_years", "missing": 0},
                    {"column": "systolic_bp", "missing": 0},
                    {"column": "moon_phase_pilot", "missing": 460},
                ],
            },
        ),
        Evidence(
            entry_id="x2",
            tool="describe",
            args={"column": "systolic_bp"},
            output={
                "column": "systolic_bp",
                "n": 500,
                "mean": 120.498186,
                "median": 118.893382,
            },
        ),
    ]


def test_screenshot_scenario_shows_readable_facts_instead_of_an_error_wall() -> None:
    text = computed_summary(stored_evidence(), max_chars=1500)
    assert "500 rows" in text and "moon_phase_pilot has 460 missing values" in text
    assert "mean 120.498" in text and "3 columns" not in text
    assert "verified" not in text and "trial" not in text


def test_unknown_payloads_cannot_supply_model_prose_or_statistics() -> None:
    item = Evidence(entry_id="x1", tool="unknown", output={"text": "Verified!", "p": 0.001})
    assert computed_summary([item], max_chars=1500) is None
    item = Evidence(
        entry_id="x1",
        tool="describe",
        output={
            "column": "x",
            "n": 10,
            "mean": float("nan"),
            "verdict": "PASS",
        },
    )
    text = computed_summary([item], max_chars=1500)
    assert "10 recorded" in text and "nan" not in text and "PASS" not in text


def test_computed_summary_obeys_the_configured_size_limit_without_partial_numbers() -> None:
    assert computed_summary(stored_evidence(), max_chars=60) == "This table contains 500 rows."


def test_old_saved_exchange_is_rendered_readably_without_changing_the_record() -> None:
    exchange = ChatExchange(
        message_id=uuid4(),
        dataset_id=uuid4(),
        created_at=datetime.now(UTC),
        question="what is this data about",
        answer=ChatAnswer(
            kind="descriptive",
            text=LEGACY_WITHHELD_TEXT,
            evidence=stored_evidence(),
            notes=["The model's wording was withheld."],
            work=ChatWork(turns=3, tool_calls=2, examined=0, input_tokens=3653, output_tokens=162),
        ),
    )
    original = exchange.model_dump_json()
    shown = ChatRepository._load(original, str(exchange.message_id), str(exchange.dataset_id))
    assert shown.answer.wording_source == "computed" and "500 rows" in shown.answer.text
    assert shown.answer.work == exchange.answer.work and shown.answer.tested is None
    assert exchange.model_dump_json() == original


def test_overview_explains_apparent_subject_before_dimensions() -> None:
    text = computed_summary(
        stored_evidence(), max_chars=1500, question="what is this data about?",
    )
    assert text.startswith("The column names suggest this is a health-related dataset")
    assert "age and systolic blood pressure" in text
    assert text.index("tentative") < text.index("500 rows")
    assert "real or synthetic" in text and "codebook" in text
    assert "clinical trial" not in text and "NHANES" not in text


def test_unrecognised_subject_is_explicitly_unknown() -> None:
    items = [Evidence(entry_id="x1", tool="overview", output={
        "rows": 50, "column_count": 2,
        "columns": [{"column": "x"}, {"column": "y"}],
    })]
    text = computed_summary(items, max_chars=1500, question="explain this dataset")
    assert text.startswith("I can't reliably tell what this dataset is about")
    assert "what each row represents" in text and "50 rows" in text


def test_count_questions_do_not_get_a_subject_explanation() -> None:
    assert not asks_about_dataset("What is the average age in this dataset?")
    text = computed_summary(stored_evidence(), max_chars=1500, question="how many rows?")
    assert text.startswith("This table contains 500 rows.")
    assert "health-related" not in text


def test_saved_count_only_overview_is_upgraded_without_changing_history() -> None:
    exchange = ChatExchange(
        message_id=uuid4(), dataset_id=uuid4(), created_at=datetime.now(UTC),
        question="what is the data about?",
        answer=ChatAnswer(
            kind="descriptive", text="This table contains 500 rows.",
            evidence=stored_evidence(), wording_source="computed",
            work=ChatWork(turns=2, tool_calls=1, examined=0, input_tokens=0, output_tokens=0),
        ),
    )
    original = exchange.model_dump_json()
    shown = ChatRepository._load(original, str(exchange.message_id), str(exchange.dataset_id))
    assert shown.answer.text.startswith("The column names suggest")
    assert shown.answer.tested is None
    assert exchange.model_dump_json() == original
