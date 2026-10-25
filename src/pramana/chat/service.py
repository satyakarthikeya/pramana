"""Chat for one dataset: prepares the table, runs a question, and keeps the testing ledger.

A claim the assistant asks to test goes through the same verification gateway as an analysis
run, under the same run slot, with the message's own UUID as the trace id. It is a family of
one, it never writes to verified memory, and the ledger records it so the count is visible.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pandas as pd
from structlog.contextvars import bound_contextvars

from pramana.analysis.cleaning import CleaningReport
from pramana.analysis.config import AnalysisConfig
from pramana.analysis.config import load_config as load_analysis_config
from pramana.analysis.reader import DataBrief
from pramana.analysis.schema_inference import SchemaProfile
from pramana.analysis.workspace.agent import ChatFn
from pramana.analysis.workspace.config import WorkspaceConfig, load_workspace_config
from pramana.api.charts import claim_chart
from pramana.api.datasets import DatasetRepository
from pramana.api.models import DatasetView, ResultRow
from pramana.api.repository import RunRepository
from pramana.api.v1 import effect_strength, permutation_count, rejection_reason
from pramana.chat.engine import ClaimRefused, VerifyFn, run_chat_turn
from pramana.chat.models import (
    ChatExchange,
    ChatLedger,
    ClaimDisclosure,
    ClaimOutcome,
    LedgerRecord,
)
from pramana.chat.store import ChatRepository
from pramana.common.llm_client import (
    ChatMessage,
    Completion,
    LLMSettings,
    LLMUnavailable,
    complete_chat,
)
from pramana.common.logging import get_logger
from pramana.contracts import CandidateInsight, ClaimType, GateOutcome, ProofObject, Verdict
from pramana.orchestration.state import RunStatus

#: Verifies one candidate. The default runs the real gateway; tests may replace it.
Verifier = Callable[[CandidateInsight, pd.DataFrame, UUID], ProofObject]


class ChatUnavailable(RuntimeError):
    """The model or its required tracing cannot be used. `str()` is safe to display."""


class ChatRateLimited(RuntimeError):
    """The account asked too many questions this hour."""


class ChatInputError(ValueError):
    """The question or the dataset cannot be used. `str()` is safe to display."""


def _chat_reason(proof: ProofObject) -> str:
    """The reason line for a chat-tested claim: honest about it being a single, uncorrected test."""
    if proof.verdict is Verdict.PASS:
        return (
            "The association met the gateway's single-test criteria and survived its "
            "applicable robustness checks. This supports an association in this table, "
            "not a causal conclusion."
        )
    if proof.gate_outcome is GateOutcome.INCONCLUSIVE and not proof.failure_reason:
        return (
            "Not statistically significant as a single test (the q-value equals the raw "
            "p-value and is not corrected for earlier tests)."
        )
    return rejection_reason(proof)


def _gateway(candidate: CandidateInsight, frame: pd.DataFrame, message_id: UUID) -> ProofObject:
    """Run the real gateway on a family of one, tracing under the message's UUID.

    The table's shape is classified first, so a question about monthly figures gets a
    null that respects their order (PLAN D6). Chat explored the whole table, so there is
    no held-out split here; the reply says the test was chosen after seeing results.
    """
    from pramana.analysis import infer_schema, load_config
    from pramana.orchestration.analysis_integration import data_structure_for
    from pramana.verification.config import load_config as load_verification_config
    from pramana.verification.gateway import verify_batch_with_summary

    structure = data_structure_for(frame, infer_schema(frame, load_config().schema_inference))
    with bound_contextvars(run_id=str(message_id)):
        proofs, summary = verify_batch_with_summary(
            [candidate], frame, load_verification_config(), structure=structure
        )
    if summary.generator_unavailable:
        raise ClaimRefused("the verifier is unavailable (check DeepSeek credentials and Langfuse).")
    if len(proofs) != 1 or proofs[0].insight_id != candidate.insight_id:
        raise ClaimRefused("the gateway did not return exactly one proof for this claim.")
    return proofs[0]


class ChatService:
    """Owns chat storage and the per-dataset table cache; holds no model or verdict logic."""

    def __init__(
        self,
        path: Path,
        datasets: DatasetRepository,
        runs: RunRepository,
        *,
        reserve: Callable[[], bool],
        release: Callable[[], None],
        chat: ChatFn | None = None,
        verifier: Verifier | None = None,
    ) -> None:
        self.repository = ChatRepository(path)
        self._datasets = datasets
        self._runs = runs
        self._reserve = reserve
        self._release = release
        self._chat = chat
        self._verifier = verifier or _gateway
        self._cache: OrderedDict[
            tuple[str, int, int], tuple[pd.DataFrame, SchemaProfile, CleaningReport]
        ] = (
            OrderedDict()
        )
        self._cache_lock = threading.Lock()
        self._lock = threading.Lock()  # guards the question counters below
        self._inflight: dict[UUID, int] = {}

    # ---- the table ------------------------------------------------------------------
    def _prepared(
        self, dataset_id: UUID, owner_id: UUID
    ) -> tuple[pd.DataFrame, SchemaProfile, str, CleaningReport]:
        """The cleaned table and its schema, built by the same path analysis runs use."""
        from pramana.analysis import clean_dataset, infer_schema, load_dataset

        path = self._datasets.file_path(dataset_id, owner_id)  # KeyError for another account
        stat = path.stat()
        key = (str(dataset_id), stat.st_mtime_ns, stat.st_size)
        with self._cache_lock:
            if key not in self._cache:
                cleaned, cleaning = clean_dataset(load_dataset(path))
                schema = infer_schema(cleaned, load_analysis_config().schema_inference)
                self._cache[key] = (cleaned, schema, cleaning)
                while len(self._cache) > 8:
                    self._cache.popitem(last=False)
            self._cache.move_to_end(key)
            frame, schema, cleaning = self._cache[key]
        return frame, schema, str(path), cleaning

    def _run_tests(self, dataset_id: UUID, owner_id: UUID) -> int:
        """Claims tested by analysis runs on this dataset, for the disclosure only."""
        total = 0
        try:
            for run in self._runs.list_runs(limit=1000, owner_id=owner_id):
                if run.dataset_id == dataset_id and run.status is RunStatus.COMPLETED:
                    results = self._runs.results(run.run_id, owner_id)
                    total += results.candidate_count if results else 0
        except Exception:
            get_logger(component="chat").warning("run_test_count_failed")
        return total

    # ---- the model ------------------------------------------------------------------
    @staticmethod
    def _default_chat(message_id: UUID) -> ChatFn:
        proposer = load_analysis_config().hypotheses.proposer
        budget = load_workspace_config().chat
        key = os.getenv(proposer.api_key_env)
        if not key:
            raise ChatUnavailable(
                f"{proposer.api_key_env} is not set, so chat is unavailable. "
                "No model request was made."
            )
        llm = LLMSettings(
            api_key=key,  # type: ignore[arg-type]
            base_url=proposer.api_base_url,
            model=proposer.api_model,
            timeout_seconds=proposer.timeout_seconds,
            max_retries=1,
        )

        def chat(messages: Sequence[ChatMessage]) -> Completion:
            try:
                return complete_chat(
                    llm,
                    messages,
                    run_id=message_id,
                    temperature=budget.temperature,
                    max_tokens=budget.max_output_tokens,
                    json_output=True,
                    thinking="disabled",
                )
            except LLMUnavailable:
                raise ChatUnavailable(
                    "The model or its required Langfuse tracing is unavailable. "
                    "Nothing was answered."
                ) from None

        return chat

    # ---- asking ---------------------------------------------------------------------
    def ask(self, dataset_id: UUID, owner_id: UUID, question: str) -> ChatExchange:
        """Answer one question and store it. Raises KeyError for a dataset not owned."""
        view = self._datasets.get(dataset_id, owner_id)
        analysis = load_analysis_config()
        workspace = load_workspace_config()
        budget = workspace.chat
        question = question.strip()
        if not question:
            raise ChatInputError("Type a question first.")
        if len(question) > budget.max_question_chars:
            raise ChatInputError(f"Keep the question under {budget.max_question_chars} characters.")
        if view.usable_columns == 0:
            raise ChatInputError("No usable measurement columns remain after cleaning.")
        # Count questions still being answered too, or parallel requests beat the hourly cap.
        with self._lock:
            used = self.repository.messages_since(owner_id) + self._inflight.get(owner_id, 0)
            if used >= budget.max_messages_per_hour:
                raise ChatRateLimited("Question limit for this hour reached. Try again later.")
            self._inflight[owner_id] = self._inflight.get(owner_id, 0) + 1
        try:
            return self._ask(dataset_id, owner_id, question, view, analysis, workspace)
        finally:
            with self._lock:
                self._inflight[owner_id] -= 1

    def _ask(
        self,
        dataset_id: UUID,
        owner_id: UUID,
        question: str,
        view: DatasetView,
        analysis: AnalysisConfig,
        workspace: WorkspaceConfig,
    ) -> ChatExchange:
        budget = workspace.chat
        try:
            frame, schema, dataset_ref, cleaning = self._prepared(dataset_id, owner_id)
        except KeyError:
            raise
        except Exception:
            raise ChatInputError("The stored file could not be read as a table.") from None

        message_id = uuid4()
        send = self._chat or self._default_chat(message_id)
        earlier_chat = self.repository.test_count(dataset_id, owner_id)
        earlier_runs = self._run_tests(dataset_id, owner_id)
        brief: DataBrief | None = view.brief

        def verify(candidate: CandidateInsight) -> ClaimOutcome:
            from pramana.verification.stats.effect_size import MAX_SENS_SLOPE_OBSERVATIONS

            if candidate.claim_type is ClaimType.TREND and len(frame) > MAX_SENS_SLOPE_OBSERVATIONS:
                raise ClaimRefused(
                    f"trend tests support at most {MAX_SENS_SLOPE_OBSERVATIONS} rows."
                )
            if not self._reserve():
                raise ClaimRefused(
                    "an analysis run or another test is using the verifier. "
                    "Ask again when it finishes."
                )
            try:
                if self.repository.test_count(dataset_id, owner_id) >= budget.max_tests_per_dataset:
                    raise ClaimRefused(
                        f"chat has already sent {budget.max_tests_per_dataset} claims to the "
                        "gateway on this dataset, which is the limit."
                    )
                try:
                    proof = self._verifier(candidate, frame, message_id)
                except ClaimRefused:
                    raise
                except Exception:
                    get_logger(component="chat", run_id=str(message_id)).error("chat_test_failed")
                    raise ClaimRefused("the test could not be run.") from None
                try:
                    chart = claim_chart(candidate, frame)
                except Exception:
                    chart = None
                row = ResultRow(
                    insight_id=proof.insight_id,
                    claim=candidate.claim,
                    proof=proof,
                    explanation=_chat_reason(proof),
                    effect_strength=effect_strength(proof),
                    n_permutations=permutation_count(proof),
                    chart=chart,
                    complete_rows=int(frame.dropna(subset=candidate.variables).shape[0]),
                )
                label: Literal["verified", "not_testable", "rejected"] = (
                    "verified"
                    if proof.verdict is Verdict.PASS
                    else "not_testable"
                    if proof.gate_outcome is GateOutcome.NOT_TESTABLE
                    else "rejected"
                )
                try:
                    record = self.repository.add_next_test(
                        lambda n: LedgerRecord(
                            test_number=n,
                            message_id=message_id,
                            created_at=datetime.now(UTC),
                            question=question,
                            claim=candidate.claim,
                            label=label,
                            q_value=proof.q_value,
                            effect_size=proof.effect_size,
                            effect_metric=(
                                proof.effect_metric.value if proof.effect_metric else None
                            ),
                            n=row.complete_rows,
                        ),
                        dataset_id,
                        owner_id,
                    )
                except Exception:
                    get_logger(component="chat", run_id=str(message_id)).error("ledger_failed")
                    raise ClaimRefused(
                        "the test ran but could not be recorded in the ledger, so it is not shown."
                    ) from None
                number = record.test_number
                return ClaimOutcome(
                    label=label,
                    row=row,
                    disclosure=ClaimDisclosure(
                        test_number=number,
                        earlier_chat_tests=number - 1,
                        earlier_run_tests=earlier_runs,
                    ),
                )
            finally:
                self._release()

        answer = run_chat_turn(
            question,
            frame,
            schema,
            analysis.hypotheses,
            workspace,
            dataset_ref=dataset_ref,
            message_id=message_id,
            chat=send,
            verify=verify,
            brief=brief,
            history=self.repository.recent_questions(
                dataset_id, owner_id, budget.history_questions
            ),
            chat_tests_so_far=earlier_chat,
        )
        if cleaning.duplicate_rows_removed:
            scope = (
                f"Data scope: these figures use {cleaning.final_shape[0]:,} of "
                f"{cleaning.original_shape[0]:,} uploaded rows after cleaning removed "
                f"{cleaning.duplicate_rows_removed:,} exact duplicate rows. "
                "If identical rows represent distinct transactions or measurements, "
                "the cleaned totals do not describe all original records. Confirm the "
                "removal or supply record identifiers before interpreting these results."
            )
            answer = answer.model_copy(update={"notes": [*answer.notes, scope]})
        exchange = ChatExchange(
            message_id=message_id,
            dataset_id=dataset_id,
            created_at=datetime.now(UTC),
            question=question,
            answer=answer,
        )
        self.repository.add_exchange(exchange, owner_id)
        return exchange

    def history(self, dataset_id: UUID, owner_id: UUID) -> list[ChatExchange]:
        self._datasets.get(dataset_id, owner_id)  # KeyError for a dataset not owned
        return self.repository.history(dataset_id, owner_id)

    def ledger(self, dataset_id: UUID, owner_id: UUID) -> ChatLedger:
        self._datasets.get(dataset_id, owner_id)
        records = self.repository.tests(dataset_id, owner_id)
        return ChatLedger(
            chat_tests=len(records),
            run_tests=self._run_tests(dataset_id, owner_id),
            limit=load_workspace_config().chat.max_tests_per_dataset,
            records=records,
        )


__all__ = [
    "ChatInputError",
    "ChatRateLimited",
    "ChatService",
    "ChatUnavailable",
    "VerifyFn",
]
