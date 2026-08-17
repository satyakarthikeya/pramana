# SCOPE_M_Karthik_Reddy.md — Work scope: Memory & System Deployment

> Owner: M. Karthik Reddy (CB.AI.U4AID23131)
> This file defines what the coding agent is building RIGHT NOW for this member.
> Context: `PROJECT.md`. Rules: `AGENTS.md`. Other members have their own SCOPE_*.md files.

## 1. What we are building

The **verified memory framework and system deployment layer**: ChromaDB-backed
long-term memory that can ONLY be written through the verification gateway's guard,
retrieval of verified lessons for new sessions (the "self-evolving" mechanism),
the FastAPI backend services around it, cloud deployment of the prototype, and the
visualisation dashboard / reporting interface.

Memory integrity is PRAMANA's differentiator — this module is where that promise
is physically enforced at the storage layer.

## 2. In scope

| # | Component | Description |
|---|---|---|
| 1 | Verified memory framework | ChromaDB collections + schema for verified lessons: lesson text, embedding, source insight_id, proof-object metadata (verdict, q_value, effect_size, evidence_score), dataset fingerprint, timestamps |
| 2 | Write path enforcement | The ONLY write API wraps the gateway's memory-guard check (`verdict == PASS`). No direct ChromaDB client access anywhere else in the codebase; enforce via module boundaries + a lint/test that greps for stray chromadb imports |
| 3 | Lesson abstraction | Turn a PASSed insight + proof object into a reusable, dataset-agnostic lesson entry (what was learned, under what conditions, with what strength) |
| 4 | Retrieval for episodes | Given a new dataset's fingerprint/profile, retrieve relevant verified lessons to seed the analysis agent (supports the batch-vs-episode self-evolution evaluation) |
| 5 | Backend services | FastAPI endpoints: upload/run, run status, results/proof objects, memory browse/search; DB integration for run metadata |
| 6 | Cloud deployment | Deploy the Dockerized stack (from B. Karthikeya's compose setup) to cloud infra; env/secret management (DeepSeek API key never in repo), persistence volumes for ChromaDB |
| 7 | Dashboard & reporting UI | Visualisation of a run: candidate insights vs verdicts, p/q-values, effect sizes, evidence scores; the demo view that shows the planted false correlation being REJECTed while real signals PASS; memory inspection view |

## 3. Out of scope (do NOT touch)

- The verdict logic itself: falsification, statistics, BH-FDR, evidence scoring, the PASS/REJECT decision (Satya Karthikeya's module) — this module CONSUMES verdicts, never produces or overrides them
- Hypothesis generation, cleaning, benchmark curation (Rohith's module)
- LangGraph graph internals, Celery task plumbing, base Docker images (B. Karthikeya's module) — deployment consumes his compose setup
- Any write path to ChromaDB that bypasses the memory guard — building one violates AGENTS.md §0

## 4. Build order (first → last)

1. **Memory schema + Pydantic lesson model** — define what a stored lesson looks like, embedding proof-object metadata; agree the guard interface with the verification member.
2. **Write path with guard enforcement** — single write function, PASS-check enforced, plus the test that fails if any other file imports chromadb directly.
3. **Lesson abstraction** — PASSed proof object → lesson entry; start rule-based/templated, keep any LLM involvement on Gemma and traced.
4. **Retrieval for episodes** — dataset fingerprinting + similarity retrieval; measure that retrieved lessons are relevant on toy cases.
5. **FastAPI endpoints** — upload/run/status/results/memory-browse; wire to the orchestration layer's run lifecycle.
6. **Dashboard MVP** — one run view: table of insights with verdict, q-value, effect size, evidence score; PASS/REJECT visually obvious (this is the demo centerpiece).
7. **Cloud deployment** — deploy compose stack, persistent ChromaDB volume, secrets via env, smoke test the full pipeline in the cloud.
8. **Demo polish** — the side-by-side view: planted false correlation REJECTed vs real relationship PASSed, with proof objects displayed.

Rationale: guard-enforced write path first because it IS the thesis; UI/deployment later
because they depend on everyone else's modules stabilizing.

## 5. Definition of done (per component)

- Type-hinted, Pydantic-validated; proof-object schema imported, not redefined
- Provably single write path: bypass test in CI (grep/import check + a runtime test that a REJECT verdict cannot be stored)
- Retrieval returns only verified lessons, each traceable back to its insight_id and proof object
- Secrets never committed; deployment reproducible from a clean clone
- Dashboard renders a full run without manual data massaging

## 6. Acceptance test (end-to-end for this module)

Given a completed run containing PASSed and REJECTed proof objects: PASSed insights appear
in ChromaDB as lessons with full provenance; attempting to store a REJECTed one raises and
stores nothing; a new episode on a similar dataset retrieves the stored lesson; the
dashboard shows the run with verdicts and stats correctly; and the same flow works on the
cloud deployment, not just locally.
