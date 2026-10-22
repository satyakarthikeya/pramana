# DeepSeek-only migration and testing checklist

Requested by B. Karthikeya on **21 October 2026**. Based on `origin/main` at
`a5ed8e3` (V1 PR #25 merged); work branch: `feat/b-karthikeya/deepseek-only`.
This is an engineering checklist, not capstone report prose or a release sign-off.

## Implementation

- [x] Pull current branch and fetch origin; branch from latest integrated main.
- [x] Replace Gemma/Ollama inference with the official DeepSeek API. Reject stale
  local-engine settings rather than silently falling back.
- [x] Use one `DEEPSEEK_API_KEY` for both structured claim proposal and separately
  prompted falsification-code generation. Current default: `deepseek-flash`;
  explicit alternative: `deepseek-v4-pro`. `DEEPSEEK_MODEL` sets both roles.
- [x] Use the shared bounded, non-redirecting transport, run-linked Langfuse
  tracing, actual token usage and secret-safe errors for both roles.
- [x] Request JSON output for proposals and reject empty/truncated/malformed,
  over-budget or contract-invalid output. Code still renders claim sentences.
- [x] Keep all statistical procedures, source validation, column policy, sandbox,
  provenance stamps, complete proofs, run-wide BH and PASS-only memory guards.
  No threshold, permutation count or verdict policy changed.
- [x] Preserve the existing website/API payloads and add useful safe messages for
  missing analysis credentials/tracing. Keys never enter frontend assets.
- [x] Set local/Docker live defaults to DeepSeek analysis + LLM verification,
  in-process V1 execution; Celery remains an explicit isolated-worker option.
- [x] Remove the Ollama dependency. No new package is required. Schema inference,
  cleaning and lesson formatting stay deterministic; they had no wired Gemma
  calls. MiniLM remains for memory-search embeddings, not generation.
- [x] Final no-Gemma audit before publication: AST scan of `src/` and `scripts/`
  found no Gemma/Ollama imports; runtime YAML and the local live profile select
  `deepseek-flash` for analysis and verification. No Ollama dependency remains.
  Historical documentation, explanatory comments and invalid-model regression
  cases may still mention Gemma; these do not call it. Installed local model
  software was not uninstalled or otherwise modified.
- [x] Retain explicitly selected deterministic/template reference modes for
  reproducible offline tests and comparisons; never use them as a fallback.
  Benchmark curation explicitly labels its reproducible candidate-count baseline;
  it must not make paid proposal calls or claim those counts are live-model results.
- [x] Update `.env.example`, setup instructions, role-policy record and this list.
- [x] Prepare the ignored local `.env`, preserving unrelated existing values.
- [x] Finish final offline verification and record exact results below.

## Credentials / resumed testing

The user entered credentials locally and explicitly resumed testing on 21 October
2026. The live checks below have now been exercised. See
[DEEPSEEK_LIVE_TEST_LOG.md](DEEPSEEK_LIVE_TEST_LOG.md) for exact run IDs, results,
remaining limitations and the extra decoy-coverage check that did not pass.
Future credential edits still belong in `.env` locally, not in chat.

Required for the live profile:

```dotenv
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
PRAMANA_ANALYSIS_ENGINE=api
PRAMANA_VERIFICATION_GENERATOR=llm
PRAMANA_API_VERIFICATION_MODE=inprocess
PRAMANA_LANGFUSE_ENABLED=true
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
```

A DeepSeek key alone is **not sufficient under the current tracing rules**.
If Langfuse credentials are unavailable, record that as a blocker; do not bypass
tracing, fabricate credentials or silently choose local logs. No credentials are
committed. The backend loads `.env` via `python -m pramana`; restart an old app
process to pick up new settings. Existing Docker/old website processes are not
evidence that the new checkout has been loaded.

## Live acceptance after the user confirms credentials are ready

- [x] Run `python scripts/check_llm_proposer.py --preflight-only`. This checks
  presence/configuration only; it does not prove funding or provider access.
- [x] Make a bounded real proposer + verification smoke run:
  `python scripts/check_llm_proposer.py --verify`. Inspect real trace IDs,
  requested/returned model metadata, token usage, stored source and complete proofs.
- [x] Restart the backend with `.venv\Scripts\python.exe -m pramana --port 8081`
  (use a free port). Open `http://127.0.0.1:8081` or connect the team's frontend to
  this backend. Do not put the provider key into browser code.
- [x] Use **Try the sample** and a second related upload. Check preview, progress,
  model-proposed claims, actual stored falsification programs, numeric p/q/effect
  outputs and all rejection reasons. A valid empty proposal batch is not a fake
  success; if no desired claim was proposed, record that limitation openly.
- [x] Validate a known strong relationship and a null/decoy claim. If the proposer
  does not emit the decoy, use a separately labelled fixed-candidate verifier
  diagnostic, not a fabricated claim that the agent proposed it. Never retry a
  completed candidate family to force significance.
- [x] Inspect JSON/CSV exports, PASS-only persisted memory, second-run historical
  hints and fresh verification; historical lessons must not become new findings
  without fresh proofs.
- [x] Test missing/invalid credentials, provider/tracing outage, malformed model
  output and sandbox refusal: safe failure/degraded status, no false PASS/writes.
  Automated fixtures cover these paths; one live invalid-key transport test also
  refused correctly. This is not a claim of live website fault injection for every case.
- [x] Measure live latency, generation failure/disagreement counts and actual
  usage. Do not report fabricated cost or claim 100% model accuracy.
- [x] Re-execute stored programs with their original seed/data for reproducibility.
- [ ] Complete affected-owner review (Rohith: analysis; Satya: gateway/tracing;
  Karthik Reddy: website/backend/config; B: orchestration) and PR checks before merge.
  Shared policy/configuration and Ollama dependency removal require explicit notice.

## Evidence / limitations

- Offline fixtures remain distinct from live evidence. Funded DeepSeek smoke,
  two browser journeys, group/trend verification, exact program replay and actual
  remote Langfuse readback are now recorded in the live test log.
- Final full suite: `python -m pytest -o addopts= --strict-markers -q`:
  **781 passed, 14 warnings in 533.45 seconds** after the prompt clarification
  (earlier migration run: 495.62 seconds). Warnings are the existing
  `TestType` enum collection notices and test-only Chroma embedding deprecations.
- `python -m ruff check src tests scripts`: passed. Targeted mypy check of the
  seven changed runtime entrypoints plus the new live audit script: passed.
  `pip check`, `git diff --check`
  and `node --check src/pramana/dashboard/static/app.js`: passed.
- Additional final focused provider/workflow checks: **25 passed in 9.08 s**;
  evaluation-condition/curation checks: **20 passed**.
- `.env` was already present and untracked/ignored. Added blank DeepSeek and
  Langfuse credential fields, explicit live-profile values and tracing enablement;
  preserved unrelated values. The initial key-entry pause ended when the user
  explicitly confirmed readiness. No credential values were printed or committed.
- The first full run exposed one offline episode test that cleared the explicit
  deterministic override and therefore selected the new hosted default. The test
  now explicitly preserves offline selection; its two-run guarded-memory check
  passes separately. The product was not changed to introduce an offline fallback.
- Provider request shape checked against official documentation on 21 October:
  [API/model names](https://api-docs.deepseek.com/),
  [JSON mode](https://api-docs.deepseek.com/guides/json_mode/),
  [explicit thinking control](https://api-docs.deepseek.com/guides/thinking_mode/).
  Thinking is explicitly disabled for bounded structured/code output. The
  configured seed reproduces statistical execution, not regenerated model text.
- Two website runs each produced 1 PASS / 5 REJECT; the live mixed-type run produced
  1 PASS / 1 REFUTED. All 14 stored programs reproduced raw p/effects exactly;
  a separate audit reproduced BH q-values for families of sizes 6, 6 and 2.
- `scripts/check_deepseek_live.py` can audit stored source and current Langfuse
  observations without more inference; `--mixed` explicitly adds one new paid run.
- Extra shuffled-column run: the model omitted the target decoy, so that coverage
  assertion failed. This limitation is recorded; it is not counted as a decoy REJECT.
  Both main website runs did propose and reject their pilot decoy.
- Clean-clone/second-machine acceptance, independent reviews,
  large benchmark conclusions and human report/freeze gates are not complete.
