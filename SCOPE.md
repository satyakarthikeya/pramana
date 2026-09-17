# SCOPE.md — Current work scope: Verification Gateway

> Owner: P.P. Satya Karthikeya (Verification & Evaluation)
> This file defines what the coding agent is building RIGHT NOW.
> Context: `PROJECT.md`. Rules: `AGENTS.md`.

## 1. What we are building

The **verification gateway**: the falsification-based layer between the analysis agent's
candidate insights and (a) the final report, (b) ChromaDB memory writes.

It is the core novelty of PRAMANA — not a supporting module. Everything downstream
trusts its verdicts.

## 2. In scope

| # | Component | Description |
|---|---|---|
| 1 | Falsification code generator | Given a candidate insight, prompt DeepSeek V4 to generate executable Python that tries to DISPROVE the claim (null-hypothesis framing) |
| 2 | Sandboxed executor | Run the generated code safely (subprocess/Celery, timeout, import whitelist) and capture the raw test statistic + p-value |
| 3 | Statistical tests library | Permutation testing and bootstrap resampling implementations the generated code can call (prefer calling our vetted functions over free-form LLM stats) |
| 4 | BH-FDR correction | Collect raw p-values across the whole run, apply Benjamini-Hochberg, produce q-values |
| 5 | Evidence scoring | Combine q-value + effect size (+ optionally test stability across resamples) into a single evidence score with a configurable threshold |
| 6 | Verdict + proof object | Emit PASS/REJECT with the full proof object schema (see PROJECT.md §5) |
| 7 | Memory guard | The single function through which ALL ChromaDB writes flow; enforces `verdict == PASS` |
| 8 | Gateway config | One config file: alpha, evidence threshold, n_permutations, n_bootstrap, timeout, seed |

## 3. Out of scope (do NOT touch)

> Ownership below follows `PROJECT.md` §4, which is the single source of truth.
> This list was written before the module reshuffle and has been corrected to match it.

- Ingestion, cleaning/profiling, hypothesis generation, benchmark curation (P. Rohith's module)
- LangGraph orchestration graph, shared state, Celery/Redis plumbing, container setup for the stack (B. Karthikeya's module)
- ChromaDB schema, lesson abstraction, retrieval, backend services, cloud deployment, dashboard (M. Karthik Reddy's module) — we only own the guard function that gates writes
- UI / frontend / dashboard
- Ablation study harness (same owner, but SEPARATE later work item — not this scope)

**Docker is tooling, not a person's module.** Nobody "owns Docker": B. Karthikeya
writes the base images/compose for the dev stack, M. Karthik Reddy deploys that same
stack to cloud, and this module only specifies the sandbox constraints the executor
container must satisfy (`AGENTS.md` §4). Treat it like any shared dependency.

## 4. Build order (first thing to work on → last)

1. **Pydantic models** for CandidateInsight and ProofObject (the contracts). Everything depends on these.
2. **Statistical tests library** — pure Python, no LLM: `permutation_test()`, `bootstrap_ci()`, with pytest known-answer tests (planted null → high p; planted effect → low p). This is the trust anchor; get it right first.
3. **BH-FDR module** — `apply_bh(p_values, alpha) -> q_values` + tests against scipy/statsmodels reference output.
4. **Evidence scorer** — deterministic function of (q_value, effect_size); thresholds from config.
5. **Sandboxed executor** — run arbitrary test code with timeout + whitelist; fail-closed on crash.
6. **Falsification code generator** — DeepSeek V4 prompt templates per claim_type (correlation / group_difference / trend); generated code should CALL the vetted stats library, not reimplement stats.
7. **Gateway orchestrator** — wire 1–6: batch insights → generate → execute → collect p's → BH → score → verdicts → proof objects.
8. **Memory guard** — thin, heavily tested function; integration point with Rohith.
9. **Langfuse tracing + structured logging** across the whole gateway.

Rationale for this order: deterministic, testable pieces first (models, stats, BH, scoring), LLM-dependent and integration pieces last. If steps 2–4 are correct, the whole gate's trustworthiness is provable; the LLM part only generates the harness around them.

## 5. Definition of done (per component)

- Type-hinted, Pydantic-validated inputs/outputs
- Pytest coverage incl. known-answer statistical tests
- Config-driven (no hardcoded thresholds/seeds)
- Structured logs with `insight_id`
- Fail-closed behavior verified (crashed/timed-out test can never yield PASS)

## 6. Acceptance test (end-to-end, mirrors the demo)

Feed the gateway a small dataframe with:
- 1 planted true relationship (strong known effect)
- 1 planted false correlation (shuffled/noise column)
- a few null variables

Expected: true relationship → PASS with sensible effect size; false correlation → REJECT;
all verdicts carry complete proof objects; nothing REJECTed appears in the memory-guard's
accepted output.

## 7. Open items (not yet done, carried deliberately)

These are known gaps in this scope, recorded so they are not mistaken for oversights.
Details and the decision each one needs are in `docs/OPEN_ISSUES.md`.

| # | Item | Blocking what |
|---|---|---|
| 1 | **Effect-size bands are PROVISIONAL.** The five per-metric bands in `configs/verification.yaml` are structural placeholders chosen to be defensible and to satisfy the test suite, not calibrated against the demo data. They decide what PASSes. | Calibrate against the real NHANES / NFHS-5 subset BEFORE step 7 (gateway). Discovering at demo time that a floor rejects the planted true relationship is the failure this exists to prevent. |
| 2 | **No categorical-vs-categorical claim type.** `EffectMetric.CRAMERS_V` is implemented, banded and tested, but no `ClaimType` can produce a contingency table, so it never fires. | A decision: add the claim type (contract change, needs announcing) or declare it out of scope here. |
| 3 | **`bootstrap_ci` is not wired to any template.** Implemented and tested (step 2), but no falsification template calls it, so no proof object ever carries a confidence interval and `TestType.BOOTSTRAP` is unreachable. | Nothing. Deliberate future work / episode-mode capability. |
| 4 | **`sens_slope` has an O(n^2) row ceiling.** All pairwise slopes are materialised, so the estimator refuses datasets above a documented row count rather than exhausting the sandbox's memory cap. | Nothing at demo scale (500-2,000 rows). Disclose the ceiling in the report's limitations section. |
| 5 | **Permutation cost is unmeasured at benchmark scale.** 10,000 resamples per insight against a 60s executor timeout is comfortable for one demo dataset; 40 datasets x many candidates is not measured. | Measure during the ablation harness (step 9), not before. |
