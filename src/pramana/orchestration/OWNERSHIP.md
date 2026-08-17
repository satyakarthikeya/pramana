# OWNERSHIP — `src/pramana/orchestration/`

**Owner:** B. Karthikeya (CB.AI.U4AID23109)
**Module:** System Architecture & Workflow
**Scope file:** `scope/SCOPE_B_Karthikeya.md`

## What lives here

The spine: the LangGraph graph, the shared state object, run lifecycle, Celery/Redis
plumbing, and the thin adapters where each member's module plugs in.

| Path | Component | Build order (SCOPE_B §4) |
|---|---|---|
| `state.py` | the single pydantic graph state | 1 |
| `graph.py`, `nodes/` | node graph + conditional edges | 2, 5 |
| `tasks.py` | Celery task defs + Redis wiring | 4 |
| `run_lifecycle.py` | run_id, config injection, retries, degraded states | 4 |
| `adapters.py` | member module ↔ graph state mapping | 6 |

Docker lives in `docker/` (see its own `OWNERSHIP.md`); Langfuse shared client lives in
`common/langfuse_client.py`.

## The role this module plays

**It calls everyone's code and implements none of it.** If graph logic starts containing
statistics, cleaning rules, or ChromaDB queries, that logic is in the wrong folder.

## Who may edit

B. Karthikeya only.

## Who may import, and what

- This package imports every other module. Nothing imports it back, except `api`, which
  triggers runs through the run lifecycle.
- `state.py` **imports** `CandidateInsight` / `ProofObject` from `pramana.contracts`.
  Redefining them in the state object is the specific failure this rule exists to prevent.

## Hard rules

1. No edge may route around the verification node. Not on retry, not on timeout, not on
   a degraded run (`AGENTS.md` §0).
2. `REJECT` skips the memory-write node.
3. Executor crash or max retries ⇒ run marked **degraded**, never a silent `PASS`.
4. `run_id` propagates into every Langfuse span so a run is traceable end to end.

## Why this module goes first

Stub nodes returning canned data let the full graph run on day one, which unblocks the
other three members immediately. Integration risk is the main failure mode of a four-person
capstone — kill it early, not in the last week.
