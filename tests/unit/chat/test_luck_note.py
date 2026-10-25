"""The chat reply states the chance that at least one of the chat claims passed by luck."""

from __future__ import annotations

from pramana.chat.engine import render_outcome
from pramana.chat.models import ClaimDisclosure, ClaimOutcome, ResultRow
from pramana.contracts import GateOutcome
from pramana.verification.config import load_config
from tests.unit.memory.test_store import _proof


def _outcome(earlier_chat_tests: int) -> ClaimOutcome:
    return ClaimOutcome(
        label="verified",
        row=ResultRow(
            insight_id="c",
            claim="y rises with x",
            proof=_proof("c", GateOutcome.SUPPORTED),
            explanation="Supported on this dataset; not a causal conclusion.",
            complete_rows=300,
        ),
        disclosure=ClaimDisclosure(
            test_number=earlier_chat_tests + 1,
            earlier_chat_tests=earlier_chat_tests,
            earlier_run_tests=0,
        ),
    )


def test_the_first_chat_claim_gets_no_luck_note() -> None:
    assert "by luck" not in render_outcome(_outcome(0))


def test_later_chat_claims_state_the_known_answer_chance_of_a_luck_pass() -> None:
    alpha = load_config().statistics.alpha
    for earlier in (1, 6):
        text = render_outcome(_outcome(earlier))
        shown = 1 - (1 - alpha) ** (earlier + 1)
        assert f"If all {earlier + 1} claims chat has tested" in text
        assert f"about {shown:.0%}" in text
