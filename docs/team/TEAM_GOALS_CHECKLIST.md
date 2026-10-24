# PRAMANA team goals and acceptance checklist

**21 October provider migration:** DeepSeek-only implementation and live testing
are tracked separately in [DEEPSEEK_ONLY_TODO.md](DEEPSEEK_ONLY_TODO.md).
Earlier Gemma acceptance below is historical evidence, not evidence of the new
provider profile. No live DeepSeek/website acceptance is claimed until that new
checklist records it.

Live update: [DEEPSEEK_LIVE_TEST_LOG.md](../evidence/DEEPSEEK_LIVE_TEST_LOG.md) records real
DeepSeek smoke, two browser journeys, group/trend execution, 14 exact program
replays and remote Langfuse readback. Final post-fix suite: **781 passed**.
One additional shuffled-decoy coverage assertion failed because the model omitted
that candidate; this is disclosed, not silently counted as a passed check.

V1 follow-up: the local application/software tasks are implemented and tested on
`feat/b-karthikeya/v1-product`: **771 tests passed**; two actual headless browser
journeys, exports, hints and PASS-only real memory passed. See
[V1 task status](../V1.md) and [V1 evidence/remaining release gates](../evidence/V1_TEST_LOG.md).
The broader goals below include work explicitly outside V1. Review/second-machine,
paid-provider and human report/freeze gates are not implied complete.

Audited: 20 October 2026. Checkout: `feat/b-karthikeya/workflow-followup`,
based on refreshed `origin/main` at `2707af0` (gateway PR #21 merged).
Earlier workflow PR #20 is merged. Ownership follows `PROJECT.md` section 4,
`OWNERSHIP.md`, `SCOPE.md` and the three member scope files.

This is an engineering handoff, not capstone report prose. A checked box means
implemented in this checkout with the stated evidence. An unchecked box means
partial, not integrated, not tested, or still required. Passing unit tests does
not establish cloud readiness, statistical calibration or research results.
Ownership below describes responsibility, not who authored every commit.

## Readiness summary

| Area | Current boundary |
|---|---|
| Local workflow | DeepSeek-only smoke, two browser journeys and group/trend run exercised; coverage limitations documented |
| Automated verification | Updated checkout: 747 passed, 10 existing warnings; earlier workflow checkpoint passed 563 |
| DeepSeek-generated execution | Default is now LLM; W1/W8 implemented upstream, one owner-reported live run; current session's paid acceptance deferred |
| Observability | Both implemented LLM roles migrated; actual DeepSeek generations/usage read back from Langfuse under matching run IDs |
| Benchmark and evaluation | 40-extract curation merged; evaluation A/D, metrics and tables implemented; B/C and study results pending |
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
- [x] W4 shared interface: `common/llm_client.py` provides OpenAI-compatible
  transport, bounded timeouts/retries/responses, usage/cost estimates, run-linked
  Langfuse generation observations and no model fallback. No new dependency.
- [x] W4 consumer consolidation implemented for structured analysis and
  falsification generation in the 21 October DeepSeek-only migration. Both now
  use the shared bounded/run-traced transport; affected-owner review and actual
  remote Langfuse acceptance remain pending, not implied by mocked tests.
- [x] Bounded completion-telemetry relay: validated worker results return through
  Redis; the trusted graph exports counts and up to 50 bounded insight metadata
  rows. No code, prompt, raw rows or exception text is relayed; no worker egress.
- [ ] Accept actual remote Langfuse delivery. Completion telemetry is not every
  worker execution log; a killed worker is represented by its caller's failure.
- [x] Preserve the new gateway batch diagnostics across queue/state/report; provider
  outages retain REJECT proofs, mark the graph degraded and skip memory without retry.
- [ ] Accept W13 with actual approved DeepSeek generation after Satya's safety
  prerequisites and tester credentials are ready.
- [ ] Demonstrate clean-clone startup on another machine and obtain required
  verification-owner review of memory/sandbox integration before merge.
- [ ] Validate realistic Celery family-size/time budgets: current 90-second task
  limit is suitable only for small families; sequential resampling and W8 comparisons
  can exceed it. Timeouts must degrade without partial-family results.

Evidence: `tests/unit/orchestration/`, `tests/integration/test_episode_workflow.py`,
`tests/integration/test_native_analysis_workflow.py`,
[workflow handoff](../archive/handoffs/B_KARTHIKEYA_COMPLETION.md), [testing phase](TESTING_PHASE.md).
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
  `SemanticRefiner` seam, not its implementation. PR #15 was closed, not merged.
- [ ] Optional Gemma cleaning suggestions applied and logged by deterministic code
  are not implemented in this checkout; keep optional scope explicit.
- [x] Benchmark pilot and 40-extract curation, provenance and per-dataset
  contamination screening are merged (PRs #16/#17). See
  [40-extract evidence](../archive/handoffs/BENCHMARK_40_HANDOFF.md); raw data remains ignored.
- [ ] W11: demonstrate that the actual LLM proposes the NHANES demo's intended
  decoy and the gateway rejects it while real relationships survive. Synthetic
  Gemma smoke acceptance is not evidence for this specific NHANES demonstration.

Evidence: `tests/unit/analysis/`, `tests/integration/test_analysis_handlers.py`,
`tests/integration/test_candidate_generation_clears_admissibility.py`,
`tests/integration/test_llm_claims_gateway.py`, [proposer guide](../archive/LLM_CLAIM_PROPOSER.md).

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
- [x] W1 static claim-column/row policy implemented upstream. It is a conservative
  AST check with documented limits, not a proof of arbitrary program semantics.
- [x] W2/W3: tests explicitly pin templates; shipped default is now LLM, with
  `PRAMANA_VERIFICATION_GENERATOR=template` for intentional offline operation.
- [ ] W5: migrate generator inference/tracing onto W4 after the shared client lands.
- [x] W8 template agreement diagnostics implemented in a separate shadow family;
  diagnostic disagreements cannot alter the primary proofs or verdicts.
- [ ] W12 at scale: owner reports one 9-claim live run with zero disagreements;
  that is not a benchmark disagreement/refusal rate.
- [x] Effect-size decision recorded: rho measured on demo, other active metrics
  checked by known-answer simulation; current V1 floors retained, not tuned for PASS.
- [x] Categorical-versus-categorical claims explicitly out of scope for V1;
  bootstrap proof intervals deferred and quadratic Sen-slope ceiling disclosed.
- [x] Planted-data builder, A/D conditions, metrics, run logging and report tables
  implemented upstream. B and C explicitly remain `NotImplementedError`.
- [ ] Complete B/C, owner-approved scoring, full benchmark runs and batch-versus-
  episode study; report actual results with overlap/power limitations.
- [x] Permutation cost measured on a representative frame upstream; see
  `scripts/measure_permutation_cost.py`. Re-measure for the deployment machine.
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
- [x] Memory/API PR #18 is merged; cloud deployment sign-off is still outstanding.

Evidence: `tests/unit/memory/`, `tests/unit/api/test_api.py`,
`src/pramana/dashboard/static/`, [memory/API handoff](../archive/handoffs/KARTHIK_LOCAL_HANDOFF.md).

## Team integration, testing and publication

- [x] Remote changes pulled and follow-up branched from `origin/main` `2707af0`.
  PRs #14, #16–#21 are merged; #15 is closed without merge. No direct main edits.
- [x] Local Docker and Gemma downloads finished; four services were running at
  final acceptance. Offline/template and actual-model results are distinguished.
- [x] Rebuilt live Gemma stack recheck: run `e1705647-c5c9-4748-80b3-2cfe6101ad61`,
  1 PASS, 1 REJECT, complete proofs and PASS-only persistence. Ignored evidence:
  `artifacts/workflow_stack_smoke.json` (local, not committed).
- [x] Earlier live worker-loss, failed-execution and persistence evidence is
  recorded with run/task IDs in [TESTING_PHASE.md](TESTING_PHASE.md).
- [x] Repository Ruff, owned-module Mypy plus stack script (25 files), `pip check`, and Compose
  configuration validation passed during this final audit.
- [x] Refreshed full-suite rerun: **747 passed, 10 existing warnings in 387.80 seconds**.
  No skips or failures. Only documentation changed after this run.
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

1. Review this additive follow-up against current main; do not reopen already merged
   dependency PRs. Obtain the required module/verification-owner review.
2. Satya and Rohith migrate their consumers onto W4; tester accepts live Langfuse
   authentication, generation/run linkage and the bounded completion relay.
3. Tester accepts distributed actual DeepSeek execution with the current W1/W8
   checks and practical batch time budgets. Use explicit template mode without keys.
4. Rohith accepts the specific LLM demo; Satya completes B/C and benchmark evaluation,
   applies approved scoring, and discloses statistical limitations.
5. Karthik Reddy accepts the browser demo, episode controls and cloud deployment;
   the team signs off the final demonstration, results and report.
