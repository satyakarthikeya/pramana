"""W8: the agreement check between the LLM path and the template path.

When the run uses the LLM generator and a claim's type has a template, the template test
is also run, as a SEPARATE shadow family, and any claim whose gate outcome differs is
flagged. The comparison is diagnostic only: the LLM-path proofs must be identical with
and without it, the shadow runs never join the real BH family, and a template crash is
recorded as `template_unavailable` rather than raised.

No network and no API key: the LLM generator is a double that returns programs labelled
`generator="llm"`.
"""

from __future__ import annotations

import json
import logging

import pytest

from pramana.contracts.enums import GateOutcome, Verdict
from pramana.verification import gateway
from pramana.verification.config import VerificationConfig
from pramana.verification.falsification.generator import generate_from_template
from pramana.verification.gateway import verify_batch_with_summary
from tests.fixtures.candidates import (
    FALSE_CORRELATION,
    NULL_CORRELATION,
    TESTABLE_CANDIDATES,
    TRUE_CORRELATION,
    TRUE_TREND,
)
from tests.fixtures.config import load_pinned_config
from tests.fixtures.frames import toy_frame

_ANCHOR = "x, y = _paired_numeric(frame)"
_SABOTAGE = (
    "x, y = _paired_numeric(frame)\n"
    "    y = __import__('numpy').random.default_rng(7).permutation(y)"
)


@pytest.fixture(scope="module")
def template_config() -> VerificationConfig:
    shipped = load_pinned_config()
    return shipped.model_copy(
        update={"statistics": shipped.statistics.model_copy(update={"n_permutations": 1000})}
    )


@pytest.fixture(scope="module")
def llm_config(template_config: VerificationConfig) -> VerificationConfig:
    return template_config.model_copy(
        update={"llm": template_config.llm.model_copy(update={"generator": "llm"})}
    )


def _as_llm(candidate, cfg):
    """The template's source, labelled as an LLM program (the faithful LLM)."""
    return generate_from_template(candidate, cfg).model_copy(update={"generator": "llm"})


def _doctored(weaken_ids: set[str]):
    """Like `_as_llm`, but the listed claims get a program that destroys the association."""

    def generate(candidate, cfg):
        program = _as_llm(candidate, cfg)
        if candidate.insight_id not in weaken_ids:
            return program
        assert _ANCHOR in program.source
        return program.model_copy(update={"source": program.source.replace(_ANCHOR, _SABOTAGE)})

    return generate


def _events(caplog, name: str) -> list[dict]:
    out = []
    for record in caplog.records:
        message = record.getMessage()
        if message.startswith("{"):
            event = json.loads(message)
            if event.get("event") == name:
                out.append({**event, "_level": record.levelno})
    return out


BATCH = [TRUE_CORRELATION, FALSE_CORRELATION, NULL_CORRELATION, TRUE_TREND]


def test_agreement_raises_no_flag(llm_config, caplog) -> None:
    with caplog.at_level(logging.INFO):
        proofs, summary = verify_batch_with_summary(
            BATCH, toy_frame(), llm_config, generate=_as_llm
        )
    assert summary.n_template_comparisons == len(BATCH)
    assert summary.n_template_unavailable == 0
    assert summary.template_disagreements == []
    assert _events(caplog, "template_disagreement") == []
    assert proofs[0].verdict is Verdict.PASS


def test_doctored_llm_program_is_flagged_in_summary_and_log(llm_config, caplog) -> None:
    with caplog.at_level(logging.INFO):
        proofs, summary = verify_batch_with_summary(
            BATCH, toy_frame(), llm_config, generate=_doctored({TRUE_CORRELATION.insight_id})
        )
    assert proofs[0].verdict is Verdict.REJECT  # the LLM-path result stands
    assert [d.insight_id for d in summary.template_disagreements] == [
        TRUE_CORRELATION.insight_id
    ]
    flagged = summary.template_disagreements[0]
    assert flagged.claim_type == TRUE_CORRELATION.claim_type.value
    assert flagged.llm_outcome == proofs[0].gate_outcome.value
    assert flagged.template_outcome == GateOutcome.SUPPORTED.value
    logged = _events(caplog, "template_disagreement")
    assert len(logged) == 1
    assert logged[0]["_level"] == logging.WARNING
    assert logged[0]["insight_id"] == TRUE_CORRELATION.insight_id


def test_the_check_never_changes_the_llm_path_result(llm_config) -> None:
    """Same doctored generator: proofs with the check (llm config) equal proofs without
    it (the same programs run under the template-config, where nothing is compared)."""
    generate = _doctored({TRUE_CORRELATION.insight_id})
    with_check, summary = verify_batch_with_summary(
        BATCH, toy_frame(), llm_config, generate=generate
    )
    template_cfg = llm_config.model_copy(
        update={"llm": llm_config.llm.model_copy(update={"generator": "template"})}
    )
    without, off_summary = verify_batch_with_summary(
        BATCH, toy_frame(), template_cfg, generate=generate
    )
    assert summary.template_disagreements
    assert off_summary.n_template_comparisons == 0
    assert [p.model_dump() for p in with_check] == [p.model_dump() for p in without]


def test_a_flag_never_turns_reject_into_pass_or_back(llm_config) -> None:
    """The doctored claim is REJECT on the LLM path while the template would PASS it."""
    proofs, summary = verify_batch_with_summary(
        BATCH, toy_frame(), llm_config, generate=_doctored({TRUE_CORRELATION.insight_id})
    )
    assert summary.template_disagreements
    assert proofs[0].verdict is Verdict.REJECT
    assert proofs[0].gate_outcome is not GateOutcome.SUPPORTED


def test_template_crash_is_recorded_not_raised(llm_config, monkeypatch, caplog) -> None:
    real_execute = gateway.execute

    def execute(program, frame, config):
        if program.generator == "template":
            raise RuntimeError("sandbox exploded")
        return real_execute(program, frame, config)

    monkeypatch.setattr(gateway, "execute", execute)
    with caplog.at_level(logging.INFO):
        proofs, summary = verify_batch_with_summary(
            BATCH, toy_frame(), llm_config, generate=_as_llm
        )
    assert summary.n_template_comparisons == 0
    assert summary.n_template_unavailable == len(BATCH)
    assert sorted(summary.template_unavailable_ids) == sorted(c.insight_id for c in BATCH)
    assert summary.template_disagreements == []
    assert proofs[0].verdict is Verdict.PASS
    assert len(_events(caplog, "template_unavailable")) == len(BATCH)


def test_template_generator_means_nothing_to_compare(template_config, caplog) -> None:
    with caplog.at_level(logging.INFO):
        _, summary = verify_batch_with_summary(
            BATCH, toy_frame(), template_config, generate=generate_from_template
        )
    assert summary.n_template_comparisons == 0
    assert summary.n_template_unavailable == 0
    assert summary.template_disagreements == []


def test_family_size_and_bh_are_unchanged(llm_config) -> None:
    proofs, summary = verify_batch_with_summary(
        BATCH, toy_frame(), llm_config, generate=_doctored({TRUE_CORRELATION.insight_id})
    )
    assert summary.n_tested == len(BATCH)
    assert all(p.n_hypotheses_in_batch == len(BATCH) for p in proofs)
    assert {p.bh_family_id for p in proofs} == {summary.bh_family_id}


def test_full_testable_batch_with_faithful_llm_has_no_disagreement(llm_config) -> None:
    _, summary = verify_batch_with_summary(
        TESTABLE_CANDIDATES, toy_frame(), llm_config, generate=_as_llm
    )
    assert summary.n_template_comparisons == len(TESTABLE_CANDIDATES)
    assert summary.template_disagreements == []
