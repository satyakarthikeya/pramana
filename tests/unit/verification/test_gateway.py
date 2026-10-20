"""Gateway batch mechanics: ordering, family membership, and the edges.

The statistical behaviour is covered by the acceptance test
(`tests/integration/test_gateway_e2e.py`). These are the cases that are cheap to test
because they never reach the executor -- and the ones most likely to be got wrong
quietly, since none of them changes a p-value.
"""

from __future__ import annotations

import pytest

from pramana.contracts.enums import GateOutcome, Verdict
from pramana.verification.config import VerificationConfig
from pramana.verification.gateway import verify_batch
from tests.fixtures.candidates import (
    INADMISSIBLE_CANDIDATES,
    UNIVERSAL_CLAIM,
    candidate,
)
from tests.fixtures.config import load_pinned_config
from tests.fixtures.frames import toy_frame


@pytest.fixture(scope="module")
def config() -> VerificationConfig:
    shipped = load_pinned_config()
    return shipped.model_copy(
        update={"statistics": shipped.statistics.model_copy(update={"n_permutations": 1000})}
    )


@pytest.fixture(scope="module")
def frame():
    return toy_frame(n_rows=60)


def test_batch_of_only_inadmissible_claims_returns_cleanly(config, frame) -> None:
    """An empty BH family is a legitimate run, not a crash: every candidate was
    refused before testing, so there is nothing to correct.
    """
    proofs = verify_batch(INADMISSIBLE_CANDIDATES, frame, config)
    assert len(proofs) == len(INADMISSIBLE_CANDIDATES)
    assert all(proof.gate_outcome is GateOutcome.NOT_TESTABLE for proof in proofs)
    assert all(proof.verdict is Verdict.REJECT for proof in proofs)
    assert all(proof.n_hypotheses_in_batch is None for proof in proofs)


def test_empty_batch_returns_empty(config, frame) -> None:
    assert verify_batch([], frame, config) == []


def test_output_order_matches_input_order(config, frame) -> None:
    """Callers zip proofs against candidates. A reordering here would silently attach
    every verdict to the wrong claim.
    """
    batch = list(reversed(INADMISSIBLE_CANDIDATES))
    proofs = verify_batch(batch, frame, config)
    assert [p.insight_id for p in proofs] == [c.insight_id for c in batch]


def test_duplicate_insight_ids_are_refused(config, frame) -> None:
    """Proof objects are keyed on `insight_id`; a duplicate would overwrite a verdict
    rather than report two.
    """
    twice = [UNIVERSAL_CLAIM, UNIVERSAL_CLAIM]
    with pytest.raises(ValueError, match="unique within a run"):
        verify_batch(twice, frame, config)


def test_family_id_is_stable_for_the_same_set(config, frame) -> None:
    first = verify_batch(INADMISSIBLE_CANDIDATES, frame, config)
    second = verify_batch(INADMISSIBLE_CANDIDATES, frame, config)
    assert {p.bh_family_id for p in first} == {p.bh_family_id for p in second}


def test_refusal_reason_reaches_the_proof_object(config, frame) -> None:
    """The agent revises from this string, so it has to name the actual problem."""
    proofs = verify_batch([UNIVERSAL_CLAIM], frame, config)
    assert "universal wording" in (proofs[0].failure_reason or "")


def test_unknown_columns_are_refused_rather_than_crashing_the_executor(config, frame) -> None:
    ghost = candidate(
        "c-ghost", "ghost is associated with age", UNIVERSAL_CLAIM.claim_type, ["age", "ghost"]
    )
    proof = verify_batch([ghost], frame, config)[0]
    assert proof.gate_outcome is GateOutcome.NOT_TESTABLE
    assert "ghost" in (proof.failure_reason or "")


# --- an LLM program that leaves out `reported_effect_metric` ---------------------


def _template_minus(line_fragment: str):
    """A generator that renders the template, then deletes the line containing a key.

    Stands in for an LLM-written program that is otherwise correct and stamped but
    omits one field of the returned dict.
    """
    from pramana.verification.falsification.generator import generate_from_template

    def generate(candidate, cfg):
        program = generate_from_template(candidate, cfg)
        kept = [ln for ln in program.source.splitlines() if line_fragment not in ln]
        assert len(kept) < len(program.source.splitlines()), "fragment not in the template"
        return program.model_copy(update={"source": "\n".join(kept) + "\n"})

    return generate


def test_control_the_untampered_template_passes(config) -> None:
    """Without this, the fail-closed test below could pass for an unrelated reason."""
    from tests.fixtures.candidates import TRUE_CORRELATION

    proofs = verify_batch([TRUE_CORRELATION], toy_frame(), config)
    assert proofs[0].verdict is Verdict.PASS


def test_program_omitting_reported_effect_metric_ends_as_reject(config) -> None:
    """A reported effect with no unit is not a complete record (AGENTS.md 3.6).

    It must come out REJECT, not PASS and not an exception, even though the program's
    p-value, effect size and stamp are all genuine.
    """
    from tests.fixtures.candidates import TRUE_CORRELATION

    proofs = verify_batch(
        [TRUE_CORRELATION],
        toy_frame(),
        config,
        generate=_template_minus('"reported_effect_metric"'),
    )
    assert len(proofs) == 1
    assert proofs[0].verdict is Verdict.REJECT
    assert proofs[0].gate_outcome is not GateOutcome.SUPPORTED
    assert "reported_effect_metric" in (proofs[0].failure_reason or "")


# --- column-check refusals are counted per claim type, for LLM programs only ---------


def _llm_labelled(mutate=None):
    """A generator rendering the template, labelled as the `llm` path.

    `mutate` edits the source, to stand in for an LLM program that drifted off the
    claim's columns.
    """
    from pramana.verification.falsification.generator import generate_from_template

    def generate(candidate, cfg):
        program = generate_from_template(candidate, cfg)
        source = program.source if mutate is None else mutate(candidate, program.source)
        return program.model_copy(update={"source": source, "generator": "llm"})

    return generate


def _summary(caplog):
    import json

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.getMessage().startswith("{")
    ]
    summaries = [e for e in events if e.get("event") == "column_check_summary"]
    assert len(summaries) == 1, "exactly one summary per batch"
    return summaries[0], [e for e in events if e.get("event") == "column_check_refused"]


def test_column_check_refusals_are_counted_per_claim_type(config, caplog) -> None:
    import logging

    from pramana.contracts.enums import ClaimType
    from tests.fixtures.candidates import TRUE_CORRELATION, candidate

    drifting = candidate(
        "c-drifts", "bmi is associated with income", ClaimType.CORRELATION, ["income", "bmi"]
    )

    def mutate(cand, source):
        if cand.insight_id != "c-drifts":
            return source
        return source.replace("frame[[VAR_X, VAR_Y]]", "frame[[VAR_X, VAR_Y, 'age']]")

    with caplog.at_level(logging.INFO):
        proofs = verify_batch(
            [TRUE_CORRELATION, drifting], toy_frame(), config, generate=_llm_labelled(mutate)
        )

    summary, refusals = _summary(caplog)
    assert summary["by_claim_type"]["correlation"] == {"llm_programs": 2, "column_check_refused": 1}
    assert [r["insight_id"] for r in refusals] == ["c-drifts"]
    assert refusals[0]["claim_type"] == "correlation"
    # The refusal is a fail-closed outcome, never a PASS.
    assert proofs[1].verdict is Verdict.REJECT
    assert proofs[0].verdict is Verdict.PASS


def test_template_programs_are_not_counted_as_llm_programs(config, caplog) -> None:
    """The metric is the LLM path's over-refusal; the reference generator must not dilute it."""
    import logging

    from tests.fixtures.candidates import TRUE_CORRELATION

    with caplog.at_level(logging.INFO):
        verify_batch([TRUE_CORRELATION], toy_frame(), config)  # config pins `template`

    summary, refusals = _summary(caplog)
    assert summary["by_claim_type"] == {}
    assert refusals == []


def test_other_failures_are_not_counted_as_column_refusals(config, caplog) -> None:
    """A crash is not an over-refusal; counting it would overstate how strict the check is."""
    import logging

    from tests.fixtures.candidates import TRUE_CORRELATION

    def crash(cand, source):
        return source.replace(
            "def falsify(frame):", "def falsify(frame):\n    raise ValueError('boom')"
        )

    with caplog.at_level(logging.INFO):
        verify_batch([TRUE_CORRELATION], toy_frame(), config, generate=_llm_labelled(crash))

    summary, refusals = _summary(caplog)
    assert summary["by_claim_type"]["correlation"] == {"llm_programs": 1, "column_check_refused": 0}
    assert refusals == []
