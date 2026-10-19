# PRAMANA team goals and acceptance checklist

Audited: 20 October 2026. Checkout: `feat/b-karthikeya/workflow-completion`.
Runtime implementation checkpoint: `7e68baf`; subsequent documentation commits
do not change that implementation. Ownership follows `PROJECT.md` section 4,
`OWNERSHIP.md`, `SCOPE.md` and the three member scope files.

This is an engineering handoff, not capstone report prose. A checked box means
implemented in this checkout with the stated evidence. An unchecked box means
partial, not integrated, not tested, or still required. Passing unit tests does
not establish cloud readiness, statistical calibration or research results.
Ownership below describes responsibility, not who authored every commit.

## Readiness summary

| Area | Current boundary |
|---|---|
| Local workflow | Working: Gemma proposals, actual template statistical execution, guarded memory and results API |
| Automated verification | 563 tests passed at the runtime checkpoint; final recheck recorded below |
| DeepSeek-generated execution | Implementation present, but live acceptance and claim-column enforcement remain pending; template mode stays explicit |
| Observability | Shared tracing and graph spans implemented; live Langfuse and isolated-worker export not accepted |
| Benchmark and evaluation | Demo builder exists; 40-dataset work is on separate review branches; evaluation modules are specifications only |
| Deployment and review | Local Docker demonstrated; cloud acceptance and required owner reviews remain outstanding |

The whole project is **not complete**. This branch is ready for review and the
documented next testing phase, not a claim that all team goals are finished.

## B. Karthikeya — CB.AI.U4AID23109

Scope: system architecture, workflow, common utilities and local Docker.

- [x] Pydantic shared state and per-run configuration; import existing candidate
  and proof contracts rather than redefining them.
- [x] LangGraph foundation and real preparation, analysis, verification, memory
  and report adapters (`src/pramana/orchestration/`).
- [x] Run IDs, lifecycle, deadlines, bounded retry policy and degraded reporting.
- [x] Celery/Redis plumbing and complete-batch gateway dispatch; no partial-family
  verdict acceptance or re-testing a completed BH family.
- [x] Fail-closed routing: unverified claims withheld, REJECT excluded from memory,
  exhausted execution failures degraded with available proofs retained.
- [x] Local API/worker/Redis/Chroma Compose stack; worker numerical thread caps
  respect unchanged sandbox limits, and Chroma mounts its actual `/data` directory.
- [x] Native analysis forwards question, run ID and historical hints to Rohith's
  configured proposer; explicit baseline and Ollama modes remain distinct.
- [x] Episode graph retrieves source-verified lessons as hints only; new claims
  receive fresh verification (`tests/integration/test_episode_workflow.py`).
- [x] W9: report separates rejected claims with their gate metadata from findings.
- [x] W13 implementation: trusted process prepares generated code or recorded
  generation failures; isolated worker receives candidate/config-bound programs
  via the gateway's public hook. Automated fixtures cover refusal paths.
- [x] Shared Langfuse construction, run context and graph observations implemented.
- [x] Real local acceptance: upload through queue to actual statistical execution,
  MiniLM embedding, guarded Chroma writes and persistence after recreation.
- [x] Live worker-loss and failed-program acceptance: degraded, zero memory writes.
- [ ] W4: consolidate the separate module-specific inference clients into one
  shared OpenAI-compatible client with timeout/retry, usage/cost and run tracing.
  `common/langfuse_client.py` is a tracing client, not that inference client.
  Coordinate consumers with Rohith and Satya; do not silently replace their calls.
- [ ] Provide a bounded worker telemetry relay without giving untrusted execution
  public network access; accept remote Langfuse delivery under one run ID.
- [ ] Accept W13 with actual approved DeepSeek generation after Satya's safety
  prerequisites and tester credentials are ready.
- [ ] Demonstrate clean-clone startup on another machine and obtain required
  verification-owner review of memory/sandbox integration before merge.

Evidence: `tests/unit/orchestration/`, `tests/integration/test_episode_workflow.py`,
`tests/integration/test_native_analysis_workflow.py`,
[workflow handoff](B_KARTHIKEYA_COMPLETION.md), [testing phase](TESTING_PHASE.md).
Your local functional workflow works; your complete tracing/model-client
acceptance boundary is not yet closed.

## P. Rohith — CB.AI.U4AID23123

Scope: dataset preparation, schema, proposals, prioritization and curation.

- [x] CSV/XLSX ingestion with limits, validation and dtype-stable loading.
- [x] Deterministic schema classification with confidence and fail-closed unknowns.
- [x] Reproducible cleaning, missing-value handling, deduplication, outlier flags,
  per-column profiling and cleaning reports.
- [x] Existing `CandidateInsight` contract emission without self-certification.
- [x] Correlation, group-difference and trend strategies; explicit offline baseline.
- [x] Configured candidate ranking/caps; analysis/gateway integration tests.
- [x] W6: structured Gemma proposer uses summaries, question and lesson hints;
  code validates claims and renders hedged text. Actual local Gemma acceptance
  succeeded, not just mocked responses.
- [x] Worker-readable cleaned dataset references exist for real gateway execution.
- [x] Seeded NHANES demo builder and planted-decoy construction have tests
  (`analysis/benchmark/demo_dataset.py`, `tests/unit/analysis/test_demo_dataset.py`).
- [ ] Integrate and accept W7 Gemma semantic refinement: this checkout has the
  `SemanticRefiner` seam, not its implementation. Separate PR #15 is under review.
- [ ] Optional Gemma cleaning suggestions applied and logged by deterministic code
  are not implemented in this checkout; keep optional scope explicit.
- [ ] Integrate and validate the benchmark pilot and 40-extract curation,
  provenance and per-dataset contamination screening (PRs #16 and #17).
  Current `benchmark/curation.py` and `contamination.py` are docstring-only.
- [ ] W11: demonstrate that the actual LLM proposes the NHANES demo's intended
  decoy and the gateway rejects it while real relationships survive. Synthetic
  Gemma smoke acceptance is not evidence for this specific NHANES demonstration.

Evidence: `tests/unit/analysis/`, `tests/integration/test_analysis_handlers.py`,
`tests/integration/test_candidate_generation_clears_admissibility.py`,
`tests/integration/test_llm_claims_gateway.py`, [proposer guide](LLM_CLAIM_PROPOSER.md).

## P.P. Satya Karthikeya — CB.AI.U4AID23128

Scope: shared contracts, verification, statistics and evaluation.

- [x] Pydantic candidate/proof contracts and explicit gate outcomes.
- [x] Known-answer tested permutation, bootstrap and effect-size library.
- [x] One BH-FDR correction across the tested family; reference tests and complete
  proof objects, including non-testable/failure cases.
- [x] Admissibility screening, metric-specific effect/direction gates and
  config-driven thresholds/seeds; evidence scoring used for ranking.
- [x] Subprocess sandbox policy, import checks, timeouts/resource limits and
  execution provenance checks; failures cannot produce PASS.
- [x] Explicit template generator and DeepSeek generation/code-checking path
  implemented; no silent template substitution on model failure.
- [x] Batch gateway, proof-preserving results and PASS-only memory guard.
- [x] Gateway/statistical integration tests exercise real code execution.
- [ ] W1: enforce generated code's claim columns and permitted rows. Library
  stamps alone do not prove that the right data was tested. This blocks treating
  the DeepSeek default as safe for user-facing operation.
- [ ] W2/W3: owner-reviewed deterministic test pinning and deliberate default
  switch only after W1 and deployment generation/execution acceptance.
- [ ] W5: migrate generator inference/tracing onto W4 after the shared client lands.
- [ ] W8/W12: template agreement checks and measured DeepSeek-versus-template
  comparison, recording model, generator and exact executed source.
- [ ] Calibrate provisional effect-size bands against the real demo; do not tune
  thresholds simply to manufacture a desired PASS or REJECT.
- [ ] Resolve categorical-versus-categorical claim scope; Cramer's V exists but
  is not reachable from a corresponding claim type.
- [ ] Explicitly retain/defer bootstrap proof intervals and disclose the
  quadratic Sen-slope row ceiling; bootstrap library tests do not imply template use.
- [ ] Build A/B/C/D evaluation, fair critic condition C, ground-truth scoring,
  precision/recall/FDR, batch-versus-episode comparison and report tables.
  `evaluation/conditions.py`, `metrics.py` and `report_tables.py` are docstrings,
  not an implemented harness. Independently shuffled columns need a planted
  relationship design that accounts for all induced associations when labeling truth.
- [ ] Run the curated benchmark and measure permutation cost/timeouts at scale;
  disclose the 40-dataset power limitation rather than inventing results.
- [ ] Accept live approved DeepSeek, replay and Langfuse evidence with the tester;
  review changes touching memory safety or sandbox behavior before merge.

Evidence: `tests/unit/contracts/`, `tests/unit/verification/`,
`tests/integration/test_gateway_e2e.py`, `src/pramana/evaluation/SPEC.md`,
`SCOPE.md` section 7 and `docs/DECISIONS_LLM_ROLES.md`.

## M. Karthik Reddy — CB.AI.U4AID23131

Scope: verified memory, API, dashboard and deployment. The memory/API implementation
in this checkout comes from Rohith's published dependency branch; module ownership
and required review remain as recorded in `OWNERSHIP.md`.

- [x] Validated lesson schema, complete source proof, fingerprint and provenance.
- [x] Guarded single write boundary; rejected batches refused, with tests against
  stray Chroma imports and direct rejection bypasses.
- [x] Rule-based lesson abstraction from PASS proofs; optional Gemma rewording
  is not required to make the existing abstraction work.
- [x] MiniLM embeddings, persistent Chroma storage and source-verified retrieval.
- [x] Retrieval is connected to the episode graph; hints never reuse old proofs
  as evidence about a new dataset.
- [x] Bounded upload, run/status/results, memory browse/search APIs and SQLite
  run metadata; failure responses withhold unverified claims.
- [x] Dashboard MVP implementation: uploads, recent runs, separate verdict tables,
  statistics/proof views and memory inspection. API/static coverage exists.
- [x] Local actual-embedding persistence and similarity search demonstrated;
  original and new records survive Chroma recreation after the volume correction.
- [ ] Add API/dashboard episode selection; graph support alone does not expose it
  through the current upload form or API run endpoint.
- [ ] Rehearse the current dashboard end to end in a browser against the final
  stack, including the designated NHANES real-versus-decoy demonstration.
- [ ] Cloud deployment, production overrides, secret management, external access
  controls, backups/recovery and cloud end-to-end acceptance are not demonstrated.
- [ ] Review the imported memory/API branch and sign off its merge and deployment.

Evidence: `tests/unit/memory/`, `tests/unit/api/test_api.py`,
`src/pramana/dashboard/static/`, [memory/API handoff](KARTHIK_LOCAL_HANDOFF.md).

## Team integration, testing and publication

- [x] Latest remote references fetched before this final audit; `origin/main`
  remains `12149d7` at audit time. No direct commit or push to main.
- [x] Integrate published memory/API PR #18 and Gemma proposer PR #19 as explicit
  dependencies on this feature branch; do not present their code as new workflow work.
- [ ] Merge those prerequisite PRs in dependency order after owner review; this
  integration PR must wait. PRs #14–#17 are separate work, not implicitly completed
  or merged by this audit.
- [x] Local Docker and Gemma downloads finished; four services were running at
  final acceptance. Offline/template and actual-model results are distinguished.
- [x] Final live Gemma stack recheck: run `8150beab-a09e-4db1-8670-1143f8c93e70`,
  1 PASS, 1 REJECT, complete proofs and PASS-only persistence. Ignored evidence:
  `artifacts/workflow_stack_smoke.json` (local, not committed).
- [x] Earlier live worker-loss, failed-execution and persistence evidence is
  recorded with run/task IDs in [TESTING_PHASE.md](TESTING_PHASE.md).
- [x] Repository Ruff, owned-module Mypy (23 files), `pip check`, and Compose
  configuration validation passed during this final audit.
- [x] Final full-suite rerun: **563 passed, 10 existing warnings in 217.38 seconds**.
  Warnings concern pytest collecting the `TestType` enum and test embedding
  deprecations; no test failed. Only documentation changed after this run.
- [ ] Tester supplies local funded provider and Langfuse credentials and completes
  the deferred checklist. Keys, raw datasets, local stores and generated artifacts
  must remain outside commits; no paid-provider acceptance is claimed.
- [x] Prepare the review branch and mandatory PR description with dependency,
  verification, configuration and limitation disclosures.
- [ ] Obtain affected-owner reviews, verification-owner approval, green CI/review
  evidence and current-main checks before merging. Publication is not permission
  to merge one's own PR; no hosted CI workflow exists in this checkout.
- [ ] Final research conclusions and human-authored report remain team work;
  respect the report's AI/plagiarism limits and do not claim unmeasured gains.

Some older status paragraphs in `PROJECT.md`, decision records and package
ownership notes predate implemented work. This checklist records observed state
without silently rewriting shared design decisions. Owners should reconcile their
status records in the PR that completes each outstanding item.

## Next actions in dependency order

1. Review/merge #18 and #19, then review this workflow branch; review schema and
   benchmark PRs separately rather than mixing unaccepted workstreams.
2. B. Karthikeya delivers W4 and bounded worker telemetry; Satya handles W5 and W1.
3. Tester accepts actual approved DeepSeek and Langfuse with the safety prerequisites
   satisfied; keep explicit template mode until then.
4. Rohith completes the specific demo and benchmark handoff; Satya runs evaluation
   and calibrates/discloses statistical limitations.
5. Karthik Reddy accepts the browser demo, episode controls and cloud deployment;
   the team signs off the final demonstration, results and report.
