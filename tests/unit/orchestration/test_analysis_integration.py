from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from pramana.orchestration.graph import build_graph, run_graph
from pramana.orchestration.integration import configured_adapters
from pramana.orchestration.state import RunStatus
from tests.fixtures.frames import toy_frame
from tests.unit.orchestration.helpers import make_run, proof


def _clear_handler_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "PRAMANA_INGEST_HANDLER",
        "PRAMANA_PREPARATION_HANDLER",
        "PRAMANA_ANALYSIS_HANDLER",
    ):
        monkeypatch.delenv(name, raising=False)


def test_native_analysis_runs_rohith_pipeline_and_persists_exact_cleaned_frame(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_handler_overrides(monkeypatch)
    source = tmp_path / "toy.csv"
    toy_frame().to_csv(source, index=False)
    memory_calls: list[list[Any]] = []

    def verify(state: Any) -> dict[str, Any]:
        return {
            "proof_objects": [
                proof(candidate.insight_id, passed=False) for candidate in state.candidate_insights
            ]
        }

    def memory_write(_state: Any, proofs: list[Any]) -> dict[str, Any]:
        memory_calls.append(proofs)
        return {"memory_receipts": []}

    adapters = configured_adapters(
        verify=verify,
        memory_write=memory_write,
        data_dir=tmp_path / "shared-data",
    )
    final = run_graph(
        make_run(str(source), user_query="Find useful relationships"),
        build_graph(adapters),
    )

    assert final.status is RunStatus.COMPLETED
    assert final.candidate_insights
    assert len(final.proof_objects) == len(final.candidate_insights)
    assert all(candidate.dataset_ref == final.dataset_ref for candidate in final.candidate_insights)
    assert final.dataset_ref is not None
    assert Path(final.dataset_ref).is_file()
    pd.testing.assert_frame_equal(pd.read_pickle(final.dataset_ref), final.dataset)
    assert final.dataset_metadata["rows"] == len(toy_frame())
    assert final.cleaning_report["final_shape"] == [len(final.dataset), len(final.dataset.columns)]
    assert final.dataset_profile
    assert final.schema_profile["n_columns"] == len(final.dataset.columns)
    assert memory_calls == []
    assert final.visited_nodes == [
        "ingest",
        "subagents",
        "analysis",
        "verification",
        "report",
        "finalize",
    ]


def test_native_analysis_failure_degrades_before_candidate_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_handler_overrides(monkeypatch)
    verification_calls = 0

    def verify(_state: Any) -> dict[str, Any]:
        nonlocal verification_calls
        verification_calls += 1
        return {"proof_objects": []}

    adapters = configured_adapters(
        verify=verify,
        memory_write=lambda _state, _proofs: {"memory_receipts": []},
        data_dir=tmp_path / "shared-data",
    )
    final = run_graph(make_run(str(tmp_path / "missing.csv")), build_graph(adapters))

    assert final.status is RunStatus.DEGRADED
    assert verification_calls == 1
    assert final.candidate_insights == []
    assert any(error.node == "ingest" for error in final.errors)
    assert "subagents" not in final.visited_nodes
    assert "analysis" not in final.visited_nodes
