# OWNERSHIP — `src/pramana/common/`

**Owner:** B. Karthikeya (CB.AI.U4AID23109) — as shared infrastructure
**Scope file:** `scope/SCOPE_B_Karthikeya.md`

## What lives here

Cross-cutting utilities every module uses:

| File | Purpose |
|---|---|
| `config.py` | load + validate `configs/*.yaml` and env vars |
| `logging.py` | structured JSON logging setup |
| `langfuse_client.py` | shared Langfuse client/config; `run_id` propagation |
| `paths.py` | canonical project paths |

## Who may edit

B. Karthikeya maintains it, but this is **shared surface** — a breaking change here breaks
all four modules at once. Announce before changing a signature; anyone may propose an
addition.

## Boundaries

- Utilities only. No business logic, no statistics, no module-specific behaviour. If a
  helper is only useful to one module, it belongs in that module.
- `config.py` **loads** configuration; it does not define thresholds. Values live in
  `configs/` (`AGENTS.md` §3.3).
- Every module emits its own Langfuse spans — this only provides the client.

## Hard rule

Inside the verification gateway, every log line carries `insight_id` (`AGENTS.md` §5).
The logging helpers here must make that easy, not optional.
