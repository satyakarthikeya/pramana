# OWNERSHIP — `src/pramana/api/`

**Owner:** M. Karthik Reddy (CB.AI.U4AID23131)
**Module:** Memory & System Deployment (backend services)
**Scope file:** `scope/SCOPE_M_Karthik_Reddy.md` §2 item 5

## What lives here

The FastAPI surface: `main.py` (app factory), `deps.py` (shared dependencies), and
routers for runs, results, and memory browsing.

| Route module | Endpoints |
|---|---|
| `routes/runs.py` | upload + start run, run status |
| `routes/results.py` | insights with their full proof objects |
| `routes/memory.py` | browse/search verified lessons (read-only) |

## Who may edit

M. Karthik Reddy only.

## Boundaries

- The API **triggers** runs through `orchestration.run_lifecycle`; it does not contain
  workflow logic itself.
- The API has **no memory write path**. Writes happen inside a run, through the guard.
- Results are served as-is from stored proof objects. The API never recomputes,
  rounds away, or re-labels a verdict.
- Secrets come from the environment (`.env` locally, secret manager in cloud).
  `.env` is gitignored and stays that way.

## Hard rule

Any endpoint that would let a caller write to memory, or mark an insight verified,
violates `AGENTS.md` §0. Don't build one, even "temporarily for the demo".
