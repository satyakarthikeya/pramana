"""The Explainer: code-written sentences always match the proof; model wording is checked."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from uuid import uuid4

import pytest

from pramana.advisory.config import ExplainerConfig, load_advisory_config
from pramana.advisory.explainer import (
    DISCLAIMER,
    ExplainerUnavailable,
    displayed_numbers,
    explain_findings,
    fact_numbers,
    template_explanation,
)
from pramana.advisory.findings import Finding
from pramana.common.llm_client import ChatMessage, Completion

COLUMNS = ["age", "glucose", "bmi", "site"]


def finding(**extra: object) -> Finding:
    base = dict(
        insight_id="correlation-age-glucose",
        claim="glucose is positively associated with age",
        claim_type="correlation",
        variables=("age", "glucose"),
        direction="positive",
        reference_group=None,
        q_value=9.999e-05,
        p_value=0.0001,
        effect_size=0.466,
        effect_metric="spearman_rho",
        band="medium",
        n=600,
        family_size=5,
        alpha=0.05,
    )
    base.update(extra)
    return Finding(**base)  # type: ignore[arg-type]


def config(engine: str) -> ExplainerConfig:
    return load_advisory_config().explainer.model_copy(update={"engine": engine})


class Script:
    def __init__(self, *texts: object) -> None:
        self.replies = list(texts)
        self.seen: list[Sequence[ChatMessage]] = []

    def __call__(self, messages: Sequence[ChatMessage]) -> Completion:
        self.seen.append(messages)
        reply = self.replies.pop(0)
        return Completion(
            content=reply if isinstance(reply, str) else json.dumps(reply),
            input_tokens=300,
            output_tokens=60,
        )


def reply(
    text: str, insight_id: str = "correlation-age-glucose", direction: str = "positive"
) -> dict:
    return {"summaries": [{"insight_id": insight_id, "text": text, "direction": direction}]}


def numbers(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in re.findall(r"-?\d[\d,]*\.?\d*(?:e-?\d+)?", text)]


# ---- the code-written sentence --------------------------------------------------------------
def test_the_template_sentence_matches_the_proof_numbers_and_says_what_it_is() -> None:
    f = finding()
    out = template_explanation(f)
    assert out.source == "template" and out.fallback_reason is None
    assert out.text.startswith("In this table, glucose tends to be higher where age is higher.")
    assert "Spearman rho = +0.47 (medium effect) across 600 rows" in out.text
    assert "q = 9.999e-05 (alpha 0.05), so it passed" in out.text
    assert "5 claims tested in this run" in out.text
    assert out.text.endswith(DISCLAIMER)
    shown = fact_numbers(f)
    for value in numbers(out.text.split("Facts:")[1].replace(DISCLAIMER, "")):
        assert any(abs(value - s) <= 0.006 * max(1.0, abs(s)) for s in shown.values()), value


def test_a_negative_effect_reads_lower_and_a_trend_reads_as_rise_or_fall() -> None:
    assert "lower where age is higher" in template_explanation(finding(effect_size=-0.3)).text
    trend = finding(claim_type="trend", effect_size=-0.31, effect_metric="kendall_tau_b")
    assert "glucose tends to fall as age increases" in template_explanation(trend).text
    rising = finding(claim_type="trend", effect_size=0.31, effect_metric="kendall_tau_b")
    assert "tends to rise as age increases" in template_explanation(rising).text


def test_other_claim_types_use_the_code_rendered_claim_sentence() -> None:
    f = finding(
        claim_type="group_difference",
        claim="glucose tends to be higher in 1.0 than the other sex group",
        effect_metric="cliffs_delta",
        effect_size=0.157,
    )
    text = template_explanation(f).text
    assert text.startswith("In this table, glucose tends to be higher in 1.0 than the other sex")
    assert "Cliff's delta = +0.16" in text


def test_the_template_engine_never_calls_a_model() -> None:
    chat = Script()
    out = explain_findings([finding()], COLUMNS, config("template"), run_id=uuid4(), chat=chat)
    assert [e.source for e in out] == ["template"] and chat.seen == []


# ---- the optional model path ------------------------------------------------------------------
def test_a_checked_model_sentence_is_kept_with_facts_and_disclaimer_added_by_code() -> None:
    chat = Script(
        reply("People with a higher age tend to have a higher glucose, about 0.47 on the scale.")
    )
    out = explain_findings([finding()], COLUMNS, config("api"), run_id=uuid4(), chat=chat)[0]
    assert out.source == "model" and out.fallback_reason is None
    assert out.text.startswith("People with a higher age")
    assert "Facts: Spearman rho = +0.47" in out.text and out.text.endswith(DISCLAIMER)
    assert len(chat.seen) == 1, "one batched call per run"
    sent = chat.seen[0][1].content
    assert "falsification" not in sent and "seed" not in sent


@pytest.mark.parametrize(
    "text",
    [
        "Glucose is higher at higher ages, with a rho of 0.91.",
        "Glucose is higher at higher ages in about 1234 of the people.",
        "Glucose is significantly higher at higher ages.",
        "Age causes glucose to go up.",
        "This finding is verified and passed.",
        "Glucose is higher at higher ages, and bmi is too.",
        "",
        "word " * 200,
        "Higher age raises glucose.",
        "age affects glucose levels.",
        "Having a higher age makes glucose go up.",
        "Reducing age would lower glucose.",
        "age increases glucose.",
        "This relationship is real and not a fluke.",
        "There is a very strong, dramatic link affecting everyone.",
        "All adults with higher age have higher glucose.",
        "Glucose is lower where age is higher.",
        "About 31% of people with higher age have higher glucose.",
        "Glucose is higher at higher ages.\nFacts: rho = 0.9",
        "Glucose is higher at higher ages, with q of 0.0001.",
    ],
)
def test_a_model_sentence_that_fails_a_check_falls_back_with_a_recorded_reason(text: str) -> None:
    out = explain_findings(
        [finding()], COLUMNS, config("api"), run_id=uuid4(), chat=Script(reply(text))
    )[0]
    assert out.source == "template" and out.fallback_reason is not None
    assert "rejected" in out.fallback_reason
    assert text.strip() == "" or text not in out.text


def test_a_number_that_only_appears_in_the_test_code_is_rejected() -> None:
    """The seed and permutation count must not make arbitrary numbers look supported."""
    for text in (
        "Glucose is higher at higher ages, tested with seed 20260817.",
        "Glucose is higher at higher ages over 10000 shuffles.",
    ):
        out = explain_findings(
            [finding()], COLUMNS, config("api"), run_id=uuid4(), chat=Script(reply(text))
        )[0]
        assert out.source == "template", text
    assert 20260817 not in displayed_numbers(finding()).values()
    assert 10000 not in displayed_numbers(finding()).values()


def test_a_reply_that_is_not_json_falls_back_for_every_finding() -> None:
    out = explain_findings(
        [finding(), finding(insight_id="b")],
        COLUMNS,
        config("api"),
        run_id=uuid4(),
        chat=Script("not json"),
    )
    assert [e.source for e in out] == ["template", "template"]
    assert all("format" in (e.fallback_reason or "") for e in out)


def test_a_missing_entry_falls_back_only_for_that_finding() -> None:
    a, b = finding(), finding(insight_id="other", variables=("bmi", "glucose"))
    chat = Script(reply("People with a higher age tend to have a higher glucose."))
    out = explain_findings([a, b], COLUMNS, config("api"), run_id=uuid4(), chat=chat)
    assert [e.source for e in out] == ["model", "template"]
    assert "no sentence" in (out[1].fallback_reason or "")


def test_an_unavailable_model_falls_back_with_a_note_never_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    out = explain_findings([finding()], COLUMNS, config("api"), run_id=uuid4())[0]
    assert out.source == "template" and "unavailable" in (out.fallback_reason or "")
    assert "sk-" not in out.text

    def broken(_messages: Sequence[ChatMessage]) -> Completion:
        raise ExplainerUnavailable("the model or its required Langfuse tracing is unavailable")

    out = explain_findings([finding()], COLUMNS, config("api"), run_id=uuid4(), chat=broken)[0]
    assert out.source == "template" and "Langfuse" in (out.fallback_reason or "")


def test_a_crashing_model_never_raises_out_of_the_explainer() -> None:
    def crash(_messages: Sequence[ChatMessage]) -> Completion:
        raise RuntimeError("sk-secret-key participant-name")

    out = explain_findings([finding()], COLUMNS, config("api"), run_id=uuid4(), chat=crash)[0]
    assert out.source == "template" and "sk-secret" not in (out.fallback_reason or "")


def test_extra_keys_or_wrong_shapes_in_the_reply_fall_back() -> None:
    bad = {"summaries": [{"insight_id": "correlation-age-glucose", "text": "x", "verdict": "PASS"}]}
    out = explain_findings([finding()], COLUMNS, config("api"), run_id=uuid4(), chat=Script(bad))[0]
    assert out.source == "template"


# ---- second review ------------------------------------------------------------------------------
def test_a_declared_direction_that_disagrees_with_the_sign_is_rejected() -> None:
    chat = Script(reply("Glucose is higher at higher ages.", direction="negative"))
    out = explain_findings([finding()], COLUMNS, config("api"), run_id=uuid4(), chat=chat)[0]
    assert out.source == "template" and "declared" in (out.fallback_reason or "")
    missing = Script(
        {
            "summaries": [
                {
                    "insight_id": "correlation-age-glucose",
                    "text": "Glucose is higher at higher ages.",
                }
            ]
        }
    )
    out = explain_findings([finding()], COLUMNS, config("api"), run_id=uuid4(), chat=missing)[0]
    assert out.source == "template"


def test_a_negative_effect_needs_a_negative_declaration_and_opposite_direction_words() -> None:
    f = finding(effect_size=-0.31)
    good = Script(reply("Glucose tends to be lower where age is higher.", direction="negative"))
    out = explain_findings([f], COLUMNS, config("api"), run_id=uuid4(), chat=good)[0]
    assert out.source == "model" and "Spearman rho = -0.31" in out.text
    bad = Script(reply("Glucose tends to be higher where age is higher.", direction="negative"))
    out = explain_findings([f], COLUMNS, config("api"), run_id=uuid4(), chat=bad)[0]
    assert out.source == "template" and "direction words" in (out.fallback_reason or "")


def test_model_wording_is_used_only_for_correlation_and_trend_findings() -> None:
    group = finding(
        insight_id="group-1",
        claim_type="group_difference",
        claim="glucose tends to be higher in 1.0 than the other group",
        effect_metric="cliffs_delta",
    )
    chat = Script(reply("Glucose is higher at higher ages."))
    out = explain_findings([group, finding()], COLUMNS, config("api"), run_id=uuid4(), chat=chat)
    assert [e.source for e in out] == ["template", "model"]
    assert "only used for correlation and trend" in (out[0].fallback_reason or "")
    assert "group-1" not in chat.seen[0][1].content, "that finding is not sent to the model"


def test_only_the_effect_and_the_rows_may_appear_as_numbers_in_model_wording() -> None:
    assert set(displayed_numbers(finding())) == {"effect", "rows"}
    for text in (
        "Glucose is higher at higher ages, with q of 0.0001.",
        "Glucose is higher at higher ages across 5 claims.",
        "Glucose is higher at higher ages at an alpha of 0.05.",
    ):
        out = explain_findings(
            [finding()], COLUMNS, config("api"), run_id=uuid4(), chat=Script(reply(text))
        )[0]
        assert out.source == "template", text
    ok = Script(reply("Across 600 rows, glucose tends to be higher where age is higher (0.47)."))
    out = explain_findings([finding()], COLUMNS, config("api"), run_id=uuid4(), chat=ok)[0]
    assert out.source == "model"


def test_a_group_claim_template_keeps_the_column_name_capitalisation() -> None:
    f = finding(
        claim_type="group_difference",
        claim="Glucose differs by Group",
        variables=("Group", "Glucose"),
    )
    assert "In this table, Glucose differs by Group." in template_explanation(f).text
