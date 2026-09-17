# Verification Gateway — Implementation Plan & Agent Prompt

Scan date: 2026-09-16. Source of truth for status: `docs/IMPLEMENTATION_STATUS.md` in the
`pramana` repo (written directly into the repo during the scan).

## Already done (don't touch, don't regenerate)

- `verification/admissibility.py` — Stage-0 screen (universal/causal claim rejection)
- `verification/stats/provenance.py` — HMAC provenance stamping
- `verification/falsification/templates.py` — deterministic per-claim-type code generator
- `configs/verification.yaml` — all thresholds/seeds

## Everything else in scope is a docstring-only stub. Build order:

1. **Contracts + config** — `contracts/enums.py`, `contracts/candidate_insight.py`,
   `contracts/proof_object.py`, `verification/config.py`. Tests:
   `tests/unit/contracts/`, `tests/unit/verification/test_config.py`.
2. **Stats library** — `stats/permutation.py`, `stats/bootstrap.py`, `stats/effect_size.py`,
   `stats/__init__.py` exports. Tests: `test_permutation.py`, `test_bootstrap.py`,
   `test_effect_size.py`.
3. **BH-FDR** — `fdr.py`. Test: `test_fdr.py`.
4. **Evidence scoring** — `evidence.py`. Test: `test_evidence.py`.
5. **Sandboxed executor** — `executor/policy.py`, `executor/runner.py`. Test: `test_executor.py`.
6. **Falsification generator (LLM path)** — `falsification/generator.py`, `prompts.py`.
   Test: `test_falsification.py`. (Deterministic default already exists — this is the
   optional DeepSeek V4 path, config-gated, genuinely lowest priority.)
7. **Gateway orchestrator** — `gateway.py`. Tests: `test_gateway.py`,
   `tests/integration/test_gateway_e2e.py`.
8. **Memory guard** — `memory_guard.py`. Test: `test_memory_guard.py`.
9. **Full suite green + acceptance test** — SCOPE.md §6 (planted true relationship PASSes,
   planted false correlation REJECTed).

Each phase only unblocks tests in its own numbered test file(s) — earlier phases are hard
dependencies of later ones (contracts → everything; stats → fdr/evidence; executor →
gateway; gateway → memory_guard).

## The prompt (paste into Claude Code / any coding agent, run locally in the repo)

Run once per phase — replace `{N}` and the file list each time. Do not hand it the whole
9-phase list at once; that invites skipping around and touching files out of order,
which `AGENTS.md` explicitly forbids.

```
You are implementing ONE phase of the PRAMANA verification gateway module. Before writing
any code:

1. Read PROJECT.md, AGENTS.md, SCOPE.md, OWNERSHIP.md, and src/pramana/verification/OWNERSHIP.md
   in full.
2. Read every test file listed below for this phase, in full — they are the spec. Do not
   guess at behavior; if a test requires something not stated in SCOPE.md or PROJECT.md,
   the test wins.
3. Only edit the files listed below. Do not touch any other member's folder
   (src/pramana/analysis, orchestration, common, memory, api, dashboard) or any file
   outside this phase's list, even if it looks related.

PHASE {N}: <one-line phase name from the plan>

Files to implement:
- <exact file paths for this phase>

Test files that define correctness for this phase (read first, do not edit):
- <exact test file paths for this phase>

Rules that apply to every line you write:
- Python 3.11+, type hints on all public functions, Pydantic models for inter-module
  payloads.
- No hardcoded thresholds or seeds — read from configs/verification.yaml via
  verification/config.py.
- Statistical functions must match the known-answer and reference-implementation tests
  exactly (e.g. statsmodels/scipy agreement) — do not approximate.
- Fail-closed: any crash, timeout, malformed output, or missing required field must be
  impossible to turn into a PASS/SUPPORTED verdict. If a test asserts this, treat it as
  non-negotiable.
- Structured (JSON) logs carrying insight_id, once logging is in scope for this phase.
- Do not weaken, delete, or skip a test to make it pass. If a test seems wrong, stop and
  tell me why instead of editing it.

When you believe the implementation is complete:
1. Run `pytest <this phase's test files> -v` and show me the full output.
2. If anything fails, fix the implementation (never the test) and re-run until green.
3. Run the FULL suite (`pytest -q`) and report whether phases before this one are still
   green (they should be untouched) — do not fix unrelated failures from later,
   not-yet-implemented phases.
4. Summarize what you implemented and stop. Wait for me before starting the next phase.
```

## Notes for the report

- Test suite (1,790 lines) already fully specifies behavior for every stub file — this
  is TDD in reverse (tests-first, by a prior session), which is unusually good position
  to be in: implementation is "make these exact tests pass," not open design.
- Corrected an earlier project-memory note: dispatch is claim-type-based (not
  dtype-based) — already resolved in the repo via `falsification/templates.py`.