# SCOPE_B_Karthikeya.md — Work scope: System Architecture & Workflow

> Owner: B. Karthikeya (CB.AI.U4AID23109)
> This file defines what the coding agent is building RIGHT NOW for this member.
> Context: `PROJECT.md`. Rules: `AGENTS.md`. Other members have their own SCOPE_*.md files.

## 1. What we are building

The **multi-agent architecture and orchestration layer** of PRAMANA: the LangGraph
graph that wires every module together, the workflow/task management around it, the
Dockerized execution environment, and the integration glue between all four members'
modules.

This module owns the "spine" of the system — it calls everyone else's code, but
implements none of their internals.

## 2. In scope

| # | Component | Description |
|---|---|---|
| 1 | LangGraph agent graph | Define the state schema and node graph: ingest → sub-agents (Gemma) → analysis agent → verification gateway → memory write → report. Conditional edges (e.g. retry on failed falsification execution, skip memory write on REJECT) |
| 2 | Shared state model | One Pydantic state object flowing through the graph; embeds the CandidateInsight / ProofObject contracts from PROJECT.md §5 — do not redefine them, import them |
| 3 | Task orchestration | Celery task definitions + Redis wiring for async steps (falsification execution runs as Celery tasks; the gateway owns the task INTERNALS, this module owns the queue plumbing) |
| 4 | Workflow management | Run lifecycle: run_id creation, per-run config injection, retries/timeouts at graph level, graceful failure states |
| 5 | Docker execution environment | Dockerfiles + docker-compose for the full stack (FastAPI app, Celery workers, Redis, ChromaDB). Sandboxing constraints for the executor container per AGENTS.md §4 |
| 6 | Integration coordination | Thin adapter layer where each member's module plugs into a graph node; integration tests that run the full graph on a tiny toy dataset |
| 7 | Langfuse wiring | Project-wide tracing setup (each module logs its own spans; this module provides the shared client/config) |

## 3. Out of scope (do NOT touch)

- Insight/hypothesis generation logic, cleaning/profiling internals (Rohith's module)
- Falsification code generation, statistical tests, BH-FDR, evidence scoring, verdicts (Satya Karthikeya's module)
- ChromaDB schema, memory abstraction logic, cloud deployment, dashboard (Karthik Reddy's module)
- Thresholds/alpha inside the verification gateway config

## 4. Build order (first → last)

1. **Shared state model + run config** — the Pydantic graph state importing the existing contracts. Everything else hangs off this.
2. **Skeleton LangGraph graph with stub nodes** — every node is a mock returning canned data; full graph runs end-to-end on day one. Teammates replace stubs with real modules as they finish.
3. **docker-compose for the dev stack** — FastAPI + Redis + Celery worker + ChromaDB containers, so all four members develop against the same environment.
4. **Celery/Redis plumbing** — async execution path for the falsification-executor node, with graph-level timeout/retry policy.
5. **Conditional edges + failure states** — REJECT path skips memory write; crashed executor → fail-closed path; max-retry → run marked degraded, never silently PASS.
6. **Integration adapters** — replace stubs with real member modules as they land; keep the adapter layer thin (call their public function, map state in/out).
7. **End-to-end integration test** — toy dataframe through the full real graph; assert a proof object exists for every candidate insight and no REJECT reaches memory.
8. **Langfuse project wiring** — shared tracing config, run_id propagated into every span.

Rationale: a running skeleton graph with stubs unblocks all three other members immediately —
integration risk is the #1 failure mode of 4-person capstones, so kill it first.

## 5. Definition of done (per component)

- Full graph runs end-to-end (stubs allowed early, real modules by integration milestone)
- Type-hinted, Pydantic-validated graph state; contracts imported, not duplicated
- docker-compose up gives a working dev environment on any machine
- Graph-level fail-closed behavior tested: no failure path can route around the verification gateway
- Integration test in CI/pytest passes on a toy dataset

## 6. Acceptance test (end-to-end)

`docker compose up`, POST a small dataset to the FastAPI endpoint, and the full graph runs:
sub-agent cleaning → analysis stubs/real → gateway → memory guard → report. Verify:
every insight has a proof object, REJECTed insights are absent from memory writes, the
run is fully traceable in Langfuse under one run_id, and killing the executor mid-run
produces a degraded-run state rather than a false PASS.
