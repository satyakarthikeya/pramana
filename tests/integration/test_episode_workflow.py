"""Historical memory is a proposal hint and cannot bypass fresh verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pramana.memory.store import ChromaLessonStore
from pramana.orchestration.adapters import inprocess_verification_adapter
from pramana.orchestration.graph import build_graph, run_graph
from pramana.orchestration.integration import configured_adapters
from pramana.orchestration.memory_integration import MemoryIntegration
from pramana.orchestration.run_lifecycle import new_run
from pramana.orchestration.state import RunStatus
from tests.fixtures.frames import toy_frame
from tests.unit.memory.test_lessons import TestEmbedding, settings_for


def test_two_runs_store_and_retrieve_real_guarded_lessons(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "PRAMANA_INGEST_HANDLER",
        "PRAMANA_PREPARATION_HANDLER",
        "PRAMANA_ANALYSIS_HANDLER",
        "PRAMANA_MEMORY_HANDLER",
        "PRAMANA_ANALYSIS_ENGINE",
    ):
        monkeypatch.delenv(name, raising=False)
    source = tmp_path / "toy.csv"
    toy_frame().to_csv(source, index=False)
    settings = settings_for(tmp_path / "chroma")
    memory = MemoryIntegration(ChromaLessonStore(settings, embedding_function=TestEmbedding()))
    seen: list[dict[str, Any]] = []
    verification_runs: list[str] = []
    from pramana.analysis import generate_candidates

    def capture(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs)
        return generate_candidates(*args, **kwargs)

    monkeypatch.setattr("pramana.analysis.generate_candidates", capture)

    def verify(state: Any) -> Any:
        verification_runs.append(str(state.run_id))
        return inprocess_verification_adapter(state)

    adapters = configured_adapters(verify=verify, memory=memory, data_dir=tmp_path)
    graph = build_graph(adapters)
    first = run_graph(new_run(str(source), user_query="Find relationships"), graph)
    assert first.status is RunStatus.COMPLETED
    assert first.memory_receipts
    assert first.lesson_hints == []
    assert seen[0]["run_id"] == first.run_id
    assert seen[0]["user_query"] == "Find relationships"

    second = run_graph(new_run(str(source), episode_mode=True), graph)
    assert second.status is RunStatus.COMPLETED
    assert second.lesson_hints
    assert seen[1]["lesson_hints"] == second.lesson_hints
    assert all(item["lesson"]["run_id"] == str(first.run_id) for item in second.retrieved_lessons)
    assert len(second.proof_objects) == len(second.candidate_insights)
    # The gateway family identifier is deterministic for identical candidate IDs.
    # Count real invocations to prove historical proofs never replace new tests.
    assert verification_runs == [str(first.run_id), str(second.run_id)]
    rejected = {p.insight_id for p in second.proof_objects if p.verdict.value == "REJECT"}
    assert rejected.isdisjoint({r["insight_id"] for r in second.memory_receipts})


def test_failed_retrieval_degrades_without_proposing_or_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRAMANA_ANALYSIS_ENGINE", raising=False)
    source = tmp_path / "toy.csv"
    toy_frame().to_csv(source, index=False)

    class UnavailableMemory(MemoryIntegration):
        def retrieve(self, state: Any) -> dict[str, Any]:
            raise ConnectionError("memory unavailable")

        def write(self, *_args: Any) -> dict[str, Any]:
            pytest.fail("A degraded episode must not write memory")

    state = new_run(str(source), episode_mode=True)
    final = run_graph(
        state,
        build_graph(
            configured_adapters(
                verify=inprocess_verification_adapter, memory=UnavailableMemory(), data_dir=tmp_path
            )
        ),
    )
    assert final.status is RunStatus.DEGRADED
    assert final.candidate_insights == []
    assert final.proof_objects == []
    assert final.report["insights"] == []
    assert any(error.node == "subagents" for error in final.errors)
