"""A generator that is UNAVAILABLE is not the same thing as a claim that is UNTESTABLE.

With no API key, a wrong provider or a dead network, every claim comes back
REJECT / NOT_TESTABLE -- exactly what a batch of genuinely untestable claims looks like.
A run could then report "no insights" when the truth is "the verifier never ran". These
tests pin that the batch result says so loudly, while every per-claim verdict stays what
it was: fail-closed, never PASS, no fallback to the template.
"""

from __future__ import annotations

import json
import logging

import pytest

from pramana.contracts.enums import GateOutcome, Verdict
from pramana.verification.config import VerificationConfig
from pramana.verification.falsification import generator
from pramana.verification.falsification.generator import (
    GeneratorError,
    GeneratorUnavailable,
    generate_from_llm,
    generate_from_template,
)
from pramana.verification.gateway import (
    GENERATOR_UNAVAILABLE_REASON_PREFIX,
    BatchSummary,
    verify_batch,
    verify_batch_with_summary,
)
from tests.fixtures.candidates import TESTABLE_CANDIDATES, TRUE_CORRELATION
from tests.fixtures.config import load_pinned_config
from tests.fixtures.frames import toy_frame


@pytest.fixture(scope="module")
def config() -> VerificationConfig:
    shipped = load_pinned_config()
    return shipped.model_copy(
        update={"statistics": shipped.statistics.model_copy(update={"n_permutations": 1000})}
    )


def _unavailable(candidate, cfg):
    raise GeneratorUnavailable("DEEPSEEK_API_KEY is not set")


def _bad_program(candidate, cfg):
    raise GeneratorError("the model's response contained no code")


def _events(caplog, name: str) -> list[dict]:
    out = []
    for record in caplog.records:
        message = record.getMessage()
        if message.startswith("{"):
            event = json.loads(message)
            if event.get("event") == name:
                out.append({**event, "_level": record.levelno})
    return out


# --- the exception type ------------------------------------------------------


def test_unavailable_is_a_generator_error() -> None:
    """Existing handlers that catch GeneratorError keep working."""
    assert issubclass(GeneratorUnavailable, GeneratorError)


def test_missing_key_raises_unavailable(monkeypatch: pytest.MonkeyPatch, config) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(GeneratorUnavailable, match="DEEPSEEK_API_KEY"):
        generator._call_deepseek("s", "u", config)


def test_wrong_provider_raises_unavailable(config) -> None:
    other = config.model_copy(update={"llm": config.llm.model_copy(update={"provider": "local"})})
    with pytest.raises(GeneratorUnavailable, match="deepseek"):
        generator._call_deepseek("s", "u", other)


def test_transport_failure_raises_unavailable(monkeypatch: pytest.MonkeyPatch, config) -> None:
    from uuid import uuid4

    from structlog.contextvars import bound_contextvars

    class _Down:
        def __init__(self, *args, **kwargs) -> None:
            raise ConnectionError("network unreachable")

    monkeypatch.setenv("DEEPSEEK_API_KEY", "not-a-real-key")
    monkeypatch.setattr(generator, "complete_chat", _Down)
    with (
        bound_contextvars(run_id=str(uuid4())),
        pytest.raises(GeneratorUnavailable, match="required tracing failed") as caught,
    ):
        generator._call_deepseek("s", "u", config)
    assert "network unreachable" not in str(caught.value)


def test_bad_model_output_is_not_unavailable(monkeypatch: pytest.MonkeyPatch, config) -> None:
    """The model answered; the answer was unusable. That is a per-claim problem."""
    llm = config.model_copy(update={"llm": config.llm.model_copy(update={"generator": "llm"})})
    monkeypatch.setattr(generator, "_call_deepseek", lambda s, u, c: "I cannot do that.")
    with pytest.raises(GeneratorError) as caught:
        generate_from_llm(TRUE_CORRELATION, llm)
    assert not isinstance(caught.value, GeneratorUnavailable)


# --- the batch result --------------------------------------------------------


def test_summary_counts_unavailable_generations_and_warns(config, caplog) -> None:
    with caplog.at_level(logging.INFO):
        proofs, summary = verify_batch_with_summary(
            TESTABLE_CANDIDATES, toy_frame(), config, generate=_unavailable
        )

    assert isinstance(summary, BatchSummary)
    assert summary.generator_unavailable_count == len(TESTABLE_CANDIDATES)
    assert summary.generator_unavailable is True
    assert summary.n_tested == 0

    warnings = _events(caplog, "generator_unavailable")
    assert len(warnings) == 1
    assert warnings[0]["_level"] == logging.WARNING
    assert warnings[0]["generator_unavailable_count"] == len(TESTABLE_CANDIDATES)

    for proof in proofs:
        assert proof.failure_reason is not None
        assert proof.failure_reason.startswith(GENERATOR_UNAVAILABLE_REASON_PREFIX)


def test_per_claim_verdicts_are_unchanged_by_unavailability(config) -> None:
    """Fail-closed per claim, exactly as before: REJECT / NOT_TESTABLE, no statistics."""
    proofs, _ = verify_batch_with_summary(
        TESTABLE_CANDIDATES, toy_frame(), config, generate=_unavailable
    )
    assert all(p.verdict is Verdict.REJECT for p in proofs)
    assert all(p.gate_outcome is GateOutcome.NOT_TESTABLE for p in proofs)
    assert all(p.p_value is None and p.n_hypotheses_in_batch is None for p in proofs)


def test_untestable_claims_are_not_counted_as_unavailable(config, caplog) -> None:
    """A model that answers badly is a different failure from a model that is absent."""
    with caplog.at_level(logging.INFO):
        _, summary = verify_batch_with_summary(
            [TRUE_CORRELATION], toy_frame(), config, generate=_bad_program
        )
    assert summary.generator_unavailable_count == 0
    assert summary.generator_unavailable is False
    assert _events(caplog, "generator_unavailable") == []


def test_a_healthy_batch_reports_nothing_unavailable(config, caplog) -> None:
    with caplog.at_level(logging.INFO):
        proofs, summary = verify_batch_with_summary(
            [TRUE_CORRELATION], toy_frame(), config, generate=generate_from_template
        )
    assert summary.generator_unavailable_count == 0
    assert summary.n_tested == 1
    assert proofs[0].verdict is Verdict.PASS
    assert _events(caplog, "generator_unavailable") == []


def test_mixed_batch_counts_only_the_unavailable_claims(config) -> None:
    def flaky(candidate, cfg):
        if candidate.insight_id == TRUE_CORRELATION.insight_id:
            return generate_from_template(candidate, cfg)
        raise GeneratorUnavailable("provider down")

    others = [c for c in TESTABLE_CANDIDATES if c.insight_id != TRUE_CORRELATION.insight_id]
    proofs, summary = verify_batch_with_summary(
        [TRUE_CORRELATION, *others], toy_frame(), config, generate=flaky
    )
    assert summary.generator_unavailable_count == len(others)
    assert summary.n_tested == 1
    assert proofs[0].verdict is Verdict.PASS


def test_verify_batch_signature_is_unchanged(config) -> None:
    """Existing callers (orchestration) keep getting a plain list of proofs."""
    proofs = verify_batch([TRUE_CORRELATION], toy_frame(), config, generate=_unavailable)
    assert isinstance(proofs, list)
    assert proofs[0].verdict is Verdict.REJECT


def test_no_key_with_the_shipped_llm_generator_is_reported_not_silent(
    monkeypatch: pytest.MonkeyPatch, config, caplog
) -> None:
    """The scenario that motivated this: generator=llm, no key, and the run looked empty."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    llm = config.model_copy(update={"llm": config.llm.model_copy(update={"generator": "llm"})})
    with caplog.at_level(logging.INFO):
        proofs, summary = verify_batch_with_summary(TESTABLE_CANDIDATES, toy_frame(), llm)
    assert summary.generator_unavailable_count == len(TESTABLE_CANDIDATES)
    assert all(p.verdict is Verdict.REJECT for p in proofs)
    assert len(_events(caplog, "generator_unavailable")) == 1
