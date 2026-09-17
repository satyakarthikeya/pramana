"""LangGraph workflow with mandatory verification and fail-closed routing."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from pramana.common.langfuse_client import get_langfuse_client, traced_run
from pramana.common.logging import bind_run_context, clear_log_context, get_logger
from pramana.contracts import Verdict
from pramana.orchestration.adapters import (
    RetryableWorkflowError,
    WorkflowAdapters,
    stub_adapters,
)
from pramana.orchestration.nodes import (
    analysis_node,
    ingest_node,
    memory_node,
    report_node,
    subagents_node,
    verification_node,
)
from pramana.orchestration.run_lifecycle import complete_run, record_failure, start_run
from pramana.orchestration.state import PramanaState, RunStatus

NodeCallable = Callable[[PramanaState], Mapping[str, Any]]


def _as_state(value: PramanaState | Mapping[str, Any]) -> PramanaState:
    if isinstance(value, PramanaState):
        return value
    validator = getattr(PramanaState, "model_validate", None)
    return validator(value) if validator is not None else PramanaState.parse_obj(value)


def _dump_state(state: PramanaState) -> dict[str, Any]:
    dumper = getattr(state, "model_dump", None)
    return dumper(mode="python") if dumper is not None else state.dict()


def _guarded(
    name: str,
    function: NodeCallable,
    *,
    retryable: tuple[type[Exception], ...] = (),
) -> NodeCallable:
    """Degrade on failure and retry only explicitly safe infrastructure crashes."""

    def run(value: PramanaState) -> Mapping[str, Any]:
        state = _as_state(value)
        if state.status == RunStatus.DEGRADED and name not in {"verification", "report"}:
            return {"visited_nodes": [*state.visited_nodes, f"{name}:skipped"]}

        max_attempts = state.runtime.run.max_node_retries + 1 if retryable else 1
        current = state
        for attempt in range(1, max_attempts + 1):
            try:
                if current.deadline_at and datetime.now(UTC) >= current.deadline_at:
                    raise TimeoutError("Graph-level deadline exceeded")
                update = dict(function(current))
                if current.deadline_at and datetime.now(UTC) >= current.deadline_at:
                    raise TimeoutError("Graph-level deadline exceeded")
                update["errors"] = list(current.errors)
                update["retry_counts"] = {**current.retry_counts, name: attempt - 1}
                return update
            except Exception as error:  # graph boundary catches module failures by design
                can_retry = isinstance(error, retryable)
                exhausted = not can_retry or attempt == max_attempts
                current = record_failure(current, name, error, attempt, exhausted=exhausted)
                get_logger(run_id=str(state.run_id), node=name).error(
                    "node_failed",
                    attempt=attempt,
                    exhausted=exhausted,
                    error_type=type(error).__name__,
                    error=str(error),
                )
                if exhausted:
                    result = _dump_state(current)
                    result["visited_nodes"] = [*current.visited_nodes, f"{name}:failed"]
                    return result
                continue
        raise AssertionError("Unreachable retry loop")

    return run


def _route_pre_verification(state: PramanaState, healthy_target: str) -> str:
    return "verification" if _as_state(state).status == RunStatus.DEGRADED else healthy_target


def _route_after_verification(state: PramanaState) -> str:
    current = _as_state(state)
    if current.status == RunStatus.DEGRADED:
        return "report"
    return (
        "memory"
        if any(proof.verdict is Verdict.PASS for proof in current.proof_objects)
        else "report"
    )


def build_graph(
    adapters: WorkflowAdapters | None = None,
    *,
    allow_stubs: bool = False,
) -> Any:
    """Compile the workflow, requiring explicit opt-in for dependency stubs."""
    from langgraph.graph import END, START, StateGraph

    selected = adapters or stub_adapters()
    if selected.is_stub and not allow_stubs:
        raise RuntimeError("Stub adapters require allow_stubs=True")

    workflow: Any = StateGraph(PramanaState)
    workflow.add_node("start", lambda state: _dump_state(start_run(_as_state(state))))
    workflow.add_node(
        "ingest", _guarded("ingest", lambda state: ingest_node(state, selected.ingest))
    )
    workflow.add_node(
        "subagents", _guarded("subagents", lambda state: subagents_node(state, selected.subagents))
    )
    workflow.add_node(
        "analysis", _guarded("analysis", lambda state: analysis_node(state, selected.analyze))
    )
    workflow.add_node(
        "verification",
        _guarded(
            "verification",
            lambda state: verification_node(state, selected.verify),
            retryable=(RetryableWorkflowError,),
        ),
    )
    workflow.add_node(
        "memory", _guarded("memory", lambda state: memory_node(state, selected.memory_write))
    )
    workflow.add_node(
        "report", _guarded("report", lambda state: report_node(state, selected.report))
    )

    def finalize(value: PramanaState) -> dict[str, Any]:
        state = _as_state(value)
        finished = complete_run(state)
        report = dict(state.report) if state.report is not None else None
        if report is not None:
            report["status"] = finished.status.value
        return {
            "status": finished.status,
            "report": report,
            "visited_nodes": [*state.visited_nodes, "finalize"],
        }

    workflow.add_node("finalize", finalize)
    workflow.add_edge(START, "start")
    workflow.add_edge("start", "ingest")
    workflow.add_conditional_edges(
        "ingest",
        lambda state: _route_pre_verification(state, "subagents"),
        {"subagents": "subagents", "verification": "verification"},
    )
    workflow.add_conditional_edges(
        "subagents",
        lambda state: _route_pre_verification(state, "analysis"),
        {"analysis": "analysis", "verification": "verification"},
    )
    workflow.add_edge("analysis", "verification")
    workflow.add_conditional_edges(
        "verification", _route_after_verification, {"memory": "memory", "report": "report"}
    )
    workflow.add_edge("memory", "report")
    workflow.add_edge("report", "finalize")
    workflow.add_edge("finalize", END)
    return workflow.compile()


def run_stub_graph(state: PramanaState) -> PramanaState:
    """Execute the safe empty-insight skeleton while teammate modules are unfinished."""
    graph = build_graph(stub_adapters(), allow_stubs=True)
    return run_graph(state, graph)


def run_graph(state: PramanaState, graph: Any) -> PramanaState:
    """Invoke a compiled graph under shared logging and Langfuse run context."""
    run_id = str(state.run_id)
    bind_run_context(run_id)
    client = get_langfuse_client(state.runtime.langfuse)
    try:
        with traced_run(client, run_id):
            return _as_state(graph.invoke(state))
    finally:
        clear_log_context()
