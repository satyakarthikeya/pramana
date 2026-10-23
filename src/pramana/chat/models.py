"""Payloads for "talk to your data": what was asked, what was answered, and how it was checked.

Every answer carries a kind that says what kind of claim it is, chosen by code and never by
the model: counts and summaries are *descriptive*, relationships looked at but not tested are
*exploratory, not verified*, and only a claim that went through the verification gateway can
be *verified* or *rejected*.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.workspace.ledger import LedgerEntry
from pramana.api.models import ResultRow

AnswerKind = Literal[
    "descriptive",  # exact counts and summaries computed by tools
    "exploratory",  # a relationship was looked at, but no significance test was run
    "verified",  # went through the gateway and passed
    "rejected",  # went through the gateway and did not pass
    "not_testable",  # the gateway could not test it
    "not_tested",  # a test was asked for but could not be run (reason in the text)
    "unanswered",  # no answer within the limits, or nothing usable came back
]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Payload):
    """One tool result the answer rests on, kept so the user can see where a number came from."""

    entry_id: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None


class ClaimDisclosure(Payload):
    """How a chat-asked claim was tested, stated plainly because it changes what q means."""

    test_number: int = Field(ge=1)
    earlier_chat_tests: int = Field(ge=0)
    earlier_run_tests: int = Field(ge=0)
    #: Chat tests each form their own family of one, so q equals the raw p-value.
    family_size: int = 1
    asked_after_seeing_results: bool = True
    corrected_for_earlier_tests: bool = False


class ClaimOutcome(Payload):
    label: Literal["verified", "rejected", "not_testable"]
    row: ResultRow
    disclosure: ClaimDisclosure


class ChatWork(Payload):
    """What the assistant did to answer, with exact counts."""

    turns: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    examined: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    entries: list[LedgerEntry] = Field(default_factory=list, max_length=20)


class ChatAnswer(Payload):
    kind: AnswerKind
    text: str
    evidence: list[Evidence] = Field(default_factory=list, max_length=12)
    tested: ClaimOutcome | None = None
    #: Plain statements added by code, for example why the model's wording was withheld.
    notes: list[str] = Field(default_factory=list, max_length=8)
    work: ChatWork


class ChatExchange(Payload):
    message_id: UUID
    dataset_id: UUID
    created_at: datetime
    question: str
    answer: ChatAnswer


class ChatQuestion(Payload):
    question: str = Field(min_length=1, max_length=4000)


class LedgerRecord(Payload):
    """One line of a dataset's chat testing ledger."""

    test_number: int = Field(ge=1)
    message_id: UUID
    created_at: datetime
    question: str
    claim: str
    label: Literal["verified", "rejected", "not_testable"]
    q_value: float | None = None
    effect_size: float | None = None
    effect_metric: str | None = None
    n: int | None = None


class ChatLedger(Payload):
    """Everything chat has tested on a dataset, and what it was compared against."""

    chat_tests: int = Field(ge=0)
    run_tests: int = Field(ge=0)
    limit: int = Field(ge=0)
    records: list[LedgerRecord]
