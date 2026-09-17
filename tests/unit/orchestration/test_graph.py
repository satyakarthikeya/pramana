from typing import Any

import pytest

from pramana.orchestration.adapters import (
    RetryableWorkflowError,
    WorkflowAdapters,
    stub_adapters,
)
from pramana.orchestration.graph import build_graph, run_stub_graph
from pramana.orchestration.run_lifecycle import new_run
from pramana.orchestration.state import RunStatus
from tests.unit.orchestration.helpers import candidate, proof


def test_stub_graph_runs_in_declared_order() -> None:
    final = run_stub_graph(new_run())
    assert final.status == RunStatus.COMPLETED
    assert final.visited_nodes == [
        "ingest",
        "subagents",
        "analysis",
        "verification",
        "report",
        "finalize",
    ]
    assert final.proof_objects == []
    assert final.memory_receipts == []
    assert final.report is not None
    assert final.report["status"] == "completed"


def test_production_graph_requires_explicit_stub_opt_in() -> None:
    with pytest.raises(RuntimeError, match="allow_stubs"):
        build_graph(stub_adapters())


def test_verification_failure_degrades_and_never_reaches_memory() -> None:
    memory_calls: list[Any] = []
    attempts = 0

    def analyze(_state: Any) -> dict[str, Any]:
        return {"candidate_insights": [candidate("candidate-1")]}

    def verify(_state: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        raise RetryableWorkflowError("executor crashed")

    def memory(_state: Any, proofs: Any) -> dict[str, Any]:
        memory_calls.append(proofs)
        return {"memory_receipts": []}

    adapters = stub_adapters()
    adapters = WorkflowAdapters(
        ingest=adapters.ingest,
        subagents=adapters.subagents,
        analyze=analyze,
        verify=verify,
        memory_write=memory,
        report=adapters.report,
    )
    graph = build_graph(adapters)
    result = graph.invoke(new_run())
    status = result.status if hasattr(result, "status") else result["status"]
    visited = result.visited_nodes if hasattr(result, "visited_nodes") else result["visited_nodes"]
    assert status == RunStatus.DEGRADED
    assert "verification:failed" in visited
    assert memory_calls == []
    assert attempts == 3


def test_transient_verification_failure_is_retained_after_retry() -> None:
    attempts = 0
    defaults = stub_adapters()

    def verify(_state: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryableWorkflowError("temporary worker loss")
        return {"proof_objects": []}

    adapters = WorkflowAdapters(
        ingest=defaults.ingest,
        subagents=defaults.subagents,
        analyze=defaults.analyze,
        verify=verify,
        memory_write=defaults.memory_write,
        report=defaults.report,
    )
    result = build_graph(adapters).invoke(new_run())
    errors = result.errors if hasattr(result, "errors") else result["errors"]
    retries = result.retry_counts if hasattr(result, "retry_counts") else result["retry_counts"]
    assert attempts == 2
    assert len(errors) == 1
    assert errors[0].node == "verification"
    assert retries["verification"] == 1


def test_reject_path_skips_memory() -> None:
    memory_calls: list[Any] = []
    rejected_candidate = candidate("candidate-1")
    rejected_proof = proof("candidate-1", passed=False)
    defaults = stub_adapters()
    adapters = WorkflowAdapters(
        ingest=defaults.ingest,
        subagents=defaults.subagents,
        analyze=lambda _state: {"candidate_insights": [rejected_candidate]},
        verify=lambda _state: {"proof_objects": [rejected_proof]},
        memory_write=lambda _state, proofs: memory_calls.append(proofs) or {},
        report=defaults.report,
    )
    graph = build_graph(adapters)
    result = graph.invoke(new_run())
    visited = result.visited_nodes if hasattr(result, "visited_nodes") else result["visited_nodes"]
    assert "memory" not in visited
    assert memory_calls == []


def test_non_retryable_analysis_failure_runs_once() -> None:
    attempts = 0
    defaults = stub_adapters()

    def broken_analysis(_state: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        raise ValueError("bad analysis payload")

    adapters = WorkflowAdapters(
        ingest=defaults.ingest,
        subagents=defaults.subagents,
        analyze=broken_analysis,
        verify=defaults.verify,
        memory_write=defaults.memory_write,
        report=defaults.report,
    )
    result = build_graph(adapters).invoke(new_run())
    status = result.status if hasattr(result, "status") else result["status"]
    assert status == RunStatus.DEGRADED
    assert attempts == 1


def test_non_retryable_verification_failure_runs_once() -> None:
    attempts = 0
    defaults = stub_adapters()

    def invalid_verification(_state: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid gateway response")

    adapters = WorkflowAdapters(
        ingest=defaults.ingest,
        subagents=defaults.subagents,
        analyze=defaults.analyze,
        verify=invalid_verification,
        memory_write=defaults.memory_write,
        report=defaults.report,
    )
    result = build_graph(adapters).invoke(new_run())
    status = result.status if hasattr(result, "status") else result["status"]
    assert status == RunStatus.DEGRADED
    assert attempts == 1
