# OWNERSHIP — `src/pramana/memory/`

**Owner:** M. Karthik Reddy (CB.AI.U4AID23131)
**Module:** Memory & System Deployment
**Scope file:** `scope/SCOPE_M_Karthik_Reddy.md`

## What lives here

ChromaDB-backed verified memory: schema, the guarded write path, lesson abstraction,
and episode-mode retrieval.

| Path | Component | Build order (SCOPE_M §4) |
|---|---|---|
| `schema.py`, `lesson.py` | collections + `Lesson` model with proof metadata | 1 |
| `store.py` | **the** write path, guard-enforced | 2 |
| `abstraction.py` | PASSed proof object → reusable lesson | 3 |
| `retrieval.py`, `fingerprint.py` | dataset fingerprint → verified lessons | 4 |

Backend services and the dashboard are the same owner but separate packages:
`src/pramana/api/`, `src/pramana/dashboard/`.

## The rule this module physically enforces

**This is the only package in the repository allowed to import `chromadb`.**
Every write goes through `store.py`, which calls
`pramana.verification.memory_guard` and stores nothing unless `verdict == PASS`.

A CI test greps the codebase for stray `chromadb` imports and fails the build. Another
test asserts that storing a `REJECT`ed proof object raises and writes nothing. Don't
delete these tests to make something pass — they *are* the thesis (`AGENTS.md` §0).

## Who may edit

M. Karthik Reddy only.

## Who may import, and what

- `orchestration` calls the memory node, which calls `store.py`.
- `api` reads through `retrieval.py` — the API has no write path.
- This module **consumes** verdicts. It never produces, recomputes, or overrides one.
  If a verdict looks wrong, that is a conversation with the verification owner, not a
  local override.

## Hard rules

1. `verdict == PASS` is checked by the guard, not re-implemented here.
2. `ProofObject` is imported from `pramana.contracts`, never redefined.
3. Every stored lesson keeps full provenance: `insight_id`, q-value, effect size,
   evidence score, dataset fingerprint, timestamp.
4. Retrieval returns verified lessons only.
5. Secrets (DeepSeek API key, cloud creds) come from env/secret manager. Never committed.
