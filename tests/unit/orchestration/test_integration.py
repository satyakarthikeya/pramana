from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from pramana.orchestration.adapters import (
    IntegrationDependencyError,
    WorkflowAdapters,
    stub_adapters,
)
from pramana.orchestration.graph import build_graph, run_graph
from pramana.orchestration.integration import (
    configured_adapters,
    load_handler,
    run_configured_workflow,
)
from pramana.orchestration.state import RunStatus
from tests.unit.orchestration.helpers import candidate, make_run, proof, runtime_config


def _install_handlers(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    analysis_module = ModuleType("pramana.analysis.test_handlers")
    memory_module = ModuleType("pramana.memory.test_handlers")

    def ingest(request: dict[str, Any]) -> dict[str, Any]:
        captured["ingest"] = request
        return {"dataset": {"raw": True}, "dataset_ref": request["dataset_ref"]}

    def prepare(request: dict[str, Any]) -> dict[str, Any]:
        captured["prepare"] = request
        return {
            "dataset": {"clean": True},
            "dataset_ref": "cleaned.parquet",
            "schema_profile": {"columns": ["x", "y"]},
        }

    def analyze(request: dict[str, Any]) -> dict[str, Any]:
        captured["analyze"] = request
        item = candidate("finding").model_copy(update={"dataset_ref": request["dataset_ref"]})
        return {"candidate_insights": [item.model_dump(mode="json")]}

    def write_verified(request: dict[str, Any]) -> dict[str, Any]:
        captured["memory"] = request
        return {
            "memory_receipts": [{"stored": item["insight_id"]} for item in request["proof_objects"]]
        }

    analysis_module.ingest = ingest  # type: ignore[attr-defined]
    analysis_module.prepare = prepare  # type: ignore[attr-defined]
    analysis_module.analyze = analyze  # type: ignore[attr-defined]
    memory_module.write_verified = write_verified  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, analysis_module.__name__, analysis_module)
    monkeypatch.setitem(sys.modules, memory_module.__name__, memory_module)
    monkeypatch.setenv("PRAMANA_INGEST_HANDLER", f"{analysis_module.__name__}:ingest")
    monkeypatch.setenv("PRAMANA_PREPARATION_HANDLER", f"{analysis_module.__name__}:prepare")
    monkeypatch.setenv("PRAMANA_ANALYSIS_HANDLER", f"{analysis_module.__name__}:analyze")
    monkeypatch.setenv("PRAMANA_MEMORY_HANDLER", f"{memory_module.__name__}:write_verified")
    return captured


def test_configured_handlers_run_full_graph_without_teammate_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_handlers(monkeypatch)
    issued = proof("finding", passed=True)
    adapters = configured_adapters(verify=lambda _state: {"proof_objects": [issued]})

    final = run_graph(
        make_run("upload.csv", user_query="Find relationships"),
        build_graph(adapters),
    )

    assert final.status is RunStatus.COMPLETED
    assert final.dataset == {"clean": True}
    assert final.dataset_ref == "cleaned.parquet"
    assert final.schema_profile == {"columns": ["x", "y"]}
    assert [item.insight_id for item in final.candidate_insights] == ["finding"]
    assert captured["analyze"]["user_query"] == "Find relationships"
    assert [item["insight_id"] for item in captured["memory"]["proof_objects"]] == ["finding"]
    assert captured["memory"]["proof_objects"][0]["verdict"] == "PASS"
    assert final.report is not None
    assert [item["insight_id"] for item in final.report["insights"]] == ["finding"]
    assert final.visited_nodes == [
        "ingest",
        "subagents",
        "analysis",
        "verification",
        "memory",
        "report",
        "finalize",
    ]


def test_handler_loader_requires_owned_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRAMANA_ANALYSIS_HANDLER", "os:path")
    with pytest.raises(IntegrationDependencyError, match="pramana.analysis"):
        load_handler("PRAMANA_ANALYSIS_HANDLER", "pramana.analysis")


def test_configured_adapters_fail_early_when_handler_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PRAMANA_INGEST_HANDLER", raising=False)
    with pytest.raises(IntegrationDependencyError, match="PRAMANA_INGEST_HANDLER"):
        configured_adapters()


def test_mismatched_candidate_dataset_degrades_before_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_handlers(monkeypatch)
    module = sys.modules["pramana.analysis.test_handlers"]
    module.analyze = lambda _request: {"candidate_insights": [candidate("wrong")]}  # type: ignore[attr-defined]
    verification_calls = 0

    def verify(_state: Any) -> dict[str, Any]:
        nonlocal verification_calls
        verification_calls += 1
        return {"proof_objects": []}

    final = run_graph(make_run("upload.csv"), build_graph(configured_adapters(verify=verify)))

    assert final.status is RunStatus.DEGRADED
    assert verification_calls == 1
    assert final.proof_objects == []
    assert any("exact cleaned dataset" in error.message for error in final.errors)


def test_run_configured_workflow_is_the_single_api_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = stub_adapters()
    ready = WorkflowAdapters(
        ingest=stub.ingest,
        subagents=stub.subagents,
        analyze=stub.analyze,
        verify=stub.verify,
        memory_write=stub.memory_write,
        report=stub.report,
    )
    monkeypatch.setattr("pramana.orchestration.integration.configured_adapters", lambda: ready)
    final = run_configured_workflow(
        "toy.csv",
        user_query="Find patterns",
        runtime=runtime_config(),
    )
    assert final.status is RunStatus.COMPLETED
    assert final.user_query == "Find patterns"


def test_ingest_handler_cannot_return_missing_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_handlers(monkeypatch)
    module = sys.modules["pramana.analysis.test_handlers"]
    module.ingest = lambda request: {"dataset": None, "dataset_ref": request["dataset_ref"]}  # type: ignore[attr-defined]
    final = run_graph(
        make_run("upload.csv"),
        build_graph(configured_adapters(verify=lambda _state: {"proof_objects": []})),
    )
    assert final.status is RunStatus.DEGRADED
    assert any("must return a dataset" in error.message for error in final.errors)


def test_configured_memory_adapter_refuses_reject_even_when_called_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_handlers(monkeypatch)
    adapters = configured_adapters(verify=lambda _state: {"proof_objects": []})
    with pytest.raises(ValueError, match="non-PASS"):
        adapters.memory_write(make_run("cleaned.parquet"), [proof("reject", passed=False)])
    assert "memory" not in captured
