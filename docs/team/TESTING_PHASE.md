# Testing phase: workflow integration

**Current profile, 21 October 2026:** follow
[DEEPSEEK_ONLY_TODO.md](DEEPSEEK_ONLY_TODO.md) first. Both LLM roles now use
DeepSeek and require Langfuse credentials. The earlier keyless/Gemma evidence
below is historical and must not be reported as live DeepSeek acceptance.

For the local **V1 product**, start with the root README, `docs/V1.md` and
[V1_TEST_LOG.md](../evidence/V1_TEST_LOG.md): no Docker/Celery/Redis or paid key is required for
the explicit template/in-process profile. The remainder of this file records the
broader deployment/live-service workflow checks, not V1 startup prerequisites.

Owner of this handoff: B. Karthikeya, CB.AI.U4AID23109.
Prepared on 20 October 2026 for the tester taking over live service checks.

Team-wide implementation and acceptance gaps are tracked in
[TEAM_GOALS_CHECKLIST.md](TEAM_GOALS_CHECKLIST.md). The follow-up from `2707af0`
implements W4's additive shared inference interface and bounded completion relay;
module-owner migration and live remote acceptance remain separate.

## Current completion boundary

The workflow implementation can be completed without API keys. The committed
default now selects LLM verification after gateway PR #21. For keyless acceptance,
explicitly set `PRAMANA_VERIFICATION_GENERATOR=template` in the shell that starts
Compose; the API and worker must match. This mode executes actual statistical tests
and guards memory writes without a paid model. It is not live DeepSeek acceptance.

The follow-up implementation is on `feat/b-karthikeya/workflow-followup`, based on
`origin/main` `2707af0`. Prior workflow PR #20 and prerequisites #18/#19 are merged;
gateway PR #21 and benchmark PRs #16/#17 are now included. Test the latest follow-up
HEAD, not the old initial workflow checkpoint `884eb4a`.

| Check | Recorded result |
|---|---|
| Full automated suite | 747 passed in 387.80 seconds after updated-main follow-up; 10 existing warnings |
| Repository Ruff lint | Passed |
| Mypy for orchestration, common and stack smoke script | Passed, 25 source files |
| Installed dependency consistency (`pip check`) | Passed |
| Docker Compose configuration validation | Passed |
| Real analysis, subprocess tests, BH-FDR and persistent Chroma in integration tests | Passed; explicitly injected test embeddings |
| Two-run retrieval and fresh verification | Passed; old proofs do not become current proofs |
| Prepared-code worker execution and model-generation failure handling | Passed with explicit test fixtures; no live provider call |
| Live Compose upload through Redis/worker/Chroma | Passed; synthetic baseline produced 1 PASS |
| Live Gemma proposer | Passed standalone (1 PASS, 3 REJECT) and through API/worker (1 PASS, 1 REJECT) |
| Live MiniLM model download/embedding/search | Passed with real MiniLM and HTTP Chroma; records survived server recreation |
| Live DeepSeek code generation | Deferred to tester; no API key supplied |
| Live Langfuse authentication and trace inspection | Deferred to tester; no credentials supplied |
| Live worker termination during execution | Passed; degraded run, zero proofs, zero memory writes |
| Live failed execution returned as a proof | Passed; REJECT proof retained, run degraded, memory skipped |

Do not promote a pending row to passed simply because the process started.
Docker and Gemma downloads completed. Successful stack smoke
results appear in ignored `artifacts/workflow_stack_smoke.json`. Successful local
proposer checks write ignored `artifacts/llm_proposer_<run_id>.json` and a run audit
under `data/runs/<run_id>/analysis_proposer.json`. Inspect the run/model/trace backend
and timestamp before treating an existing artifact as evidence for this checkout.

### Runtime fixes and live evidence, 20 October 2026

- Worker BLAS pools initially reserved about 2.36 GB of virtual address space,
  exceeding the sandbox's 1 GB cap before a test could run. The image-owned
  `worker_sitecustomize.py` now caps numerical threads before imports in both the
  worker and its sanitized Python children. Measured virtual memory fell to about
  479 MB; a real test succeeded with the original limits. No statistical threshold,
  resource cap, import whitelist or worker network isolation was relaxed.
- Exhausted execution failures previously carried REJECT proofs but could leave
  the graph marked completed. Orchestration now retains those proofs, marks the run
  degraded and skips memory. It does not repeat the tested BH family.
- Chroma 1.5 writes to `/data`. The original legacy mount at `/chroma/chroma` did
  not persist its actual database. Compose now mounts `chroma-data:/data`. Existing
  data was backed up at ignored `data/chroma-volume-migration-backup/` and copied
  into the named volume before recreation; no records were discarded.
- Baseline Docker run `02df9d81-426c-44ff-9341-f1627fce9c3f`: completed, 1 PASS,
  real MiniLM embedding and guarded Chroma write.
- Gemma Docker run `54667f3e-70ca-4418-be6a-c67ddd8dd444`: completed, 1 PASS and
  1 REJECT. API environment selected Ollama and the run's proposer audit exists.
  A repeat after the volume fix, `9416a260-0a7f-4ea7-b803-8fe419cdb081`, also
  produced 1 PASS and 1 REJECT. `artifacts/workflow_stack_smoke.json` records
  that latest run.
- Standalone Gemma run `952803af-9ae9-46ca-8fc7-ba5a8ad49a17`: 4 proposals,
  1 PASS and 3 REJECT, with an explicit local audit.
- Interrupted-worker run `c7566dd2-316a-4904-bade-6d8b2e4bcf8b`, task
  `384013fa-523e-41d8-b5e0-e3f732d18b5f`: the worker was killed after dispatch
  while a synthetic hanging program ran. The graph ended degraded with no proofs
  or memory writes. Evidence: ignored `artifacts/worker_loss_smoke.json`.
- Failed-program run `034a0975-7b47-479a-baf4-29061cc4947a`: a synthetic exception
  produced a REJECT proof, degraded status and zero memory writes. Evidence:
  ignored `artifacts/executor_failure_smoke.json`.
- After Chroma recreation, records `56c20d186fb24362fe257017` and
  `d2a32ea972ae5ae52497dce7` remained present and retrievable with PASS proofs.
  A second recreation preserved newly written record `751df57fefe8123db9c4824a`
  from the post-fix run, confirming new writes use the persistent volume too.
  The API, worker, Redis and Chroma were left running. The API currently uses
  explicit Gemma analysis and template verification; reproducing that selection
  after another Compose recreation requires the engine override below.

These are keyless live acceptance results. DeepSeek and Langfuse remain deferred.

## 1. Reproduce the keyless checks

Run these PowerShell commands from the repository root, using Python 3.11+:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest --tb=short
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src/pramana/orchestration src/pramana/common scripts/check_workflow_stack.py
.venv/Scripts/python.exe -m pip check
```

Do not edit shared verification YAML to run offline. The pytest suite pins templates;
for standalone keyless commands set `$env:PRAMANA_VERIFICATION_GENERATOR = "template"`.
Leave `PRAMANA_ANALYSIS_ENGINE` unset, or explicitly select `deterministic`.
The normal suite uses fixtures for model responses. Model/provider availability
and provider quality remain separate from this result.

Focused workflow checks:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/orchestration tests/integration/test_episode_workflow.py tests/integration/test_native_analysis_workflow.py
```

Expected: every candidate has a proof; only PASS proofs reach guarded storage and
the findings report; retrieval failures degrade the run; historical lessons remain
hints; missing/mismatched prepared programs and configs are refused. A failed or
timed-out verification must never create a PASS.

## 2. Live Docker stack without paid keys

Start Docker Desktop. If `.env` does not exist, copy `.env.example` to `.env`.
Preserve an existing `.env`; do not overwrite someone else's local configuration.
Blank DeepSeek and Langfuse credentials are acceptable for this offline mode.

```powershell
docker compose -f docker/docker-compose.yml config --quiet
docker compose -f docker/docker-compose.yml up --build -d
docker compose -f docker/docker-compose.yml ps
.venv/Scripts/python.exe scripts/check_workflow_stack.py --startup-timeout 600 --run-timeout 600
```

On this machine Docker's executable is at:
`C:/Users/karth/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe`.
Use that executable if `docker` is absent from PATH.

The smoke script uploads synthetic data to `http://localhost:8080`, polls for
completion, validates all returned proofs and checks persisted PASS-only lessons.
Expected: completed run, at least one PASS, zero unverified candidates and no
rejected proof in memory for that run. Inspect the saved JSON proof records.
Visit the dashboard at `http://localhost:8080` and inspect the same run's results.
`/health` establishes API liveness only, not that Redis, Chroma or models work.

Compose explicitly selects Celery verification and HTTP Chroma. API client and
server both use Chroma 1.5.9. The execution worker stays on its internal queue
network with read-only data, bounded temporary storage and resource limits.
First real embedding use may download MiniLM; that requires trusted API egress.
Do not substitute test embeddings for this live acceptance check.

For worker-loss acceptance, use only a disposable synthetic test run: wait until
the worker is actively processing verification, terminate that worker, then check
the run and restart the worker. The workflow must either recover through the
configured crash retry or finish degraded/failed. A missing/partial family must
never become a successful run or unverified memory write. Save the run ID, task ID,
logs and final status. A termination after the task already finished is not evidence
for this failure test. Do not remove data volumes to perform this check.

## 3. Live local Gemma, still without paid keys

Ollama was reachable during setup, but initially only Llama was installed. The
configured proposer requires Gemma. Never substitute Llama silently.

```powershell
ollama list
ollama pull gemma2:2b
.venv/Scripts/python.exe scripts/check_llm_proposer.py --preflight-only --trace-backend local
.venv/Scripts/python.exe scripts/check_llm_proposer.py --verify --trace-backend local
```

Local audit mode is explicitly authorized in the current repository rules and
needs no Langfuse credentials. Check the report records the actual Gemma model,
the run UUID and local audit backend. Its proposals still require fresh gateway
verification. No number asserted by the model may become statistical evidence.

For the container's analysis stage, explicitly activate Gemma before recreating
the API service:

```powershell
$env:PRAMANA_ANALYSIS_ENGINE = "ollama"
$env:PRAMANA_VERIFICATION_GENERATOR = "template"
docker compose -f docker/docker-compose.yml up --build -d
.venv/Scripts/python.exe scripts/check_workflow_stack.py --startup-timeout 600 --run-timeout 600
```

The API reaches host Ollama through `host.docker.internal:11434`. Its validated
model defaults to `gemma2:2b`. To return to the offline baseline, unset this override
and recreate the API service. The standalone proposer smoke's local audit does not
establish that the API used Gemma; inspect the API run's analysis audit as well.

## 4. Credentials required only for deferred live services

| Purpose | Local environment values needed |
|---|---|
| DeepSeek/provider inference | `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL` |
| Langfuse export and trace acceptance | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` |
| Offline/template verification | None of the above |
| Gemma proposer with explicit local audit | No paid API or Langfuse key; installed Ollama model required |

Put real values only in the ignored `.env` or the tester's environment. Never
commit them, paste them into issue/PR descriptions or include them in screenshots.
Compose reads `.env` via `env_file`; restart/recreate services after changing it.
Standalone Python entrypoints may need `python-dotenv` loaded before importing
modules that read environment configuration. The proposer smoke script already
loads the root `.env`.

The provider endpoint and model identifier must agree. The checked-in model value
`deepseek-chat` is the upstream verification owner's current selection. This session
has not validated it against a funded account; confirm the endpoint/model pairing
and approved model with the provider and verification owner before live testing.
Do not assume an OpenRouter model identifier works with a direct DeepSeek endpoint.
For direct DeepSeek, the configured base URL is `https://api.deepseek.com`; for an
OpenRouter key use its compatible endpoint, `https://openrouter.ai/api/v1`.
No additional OpenAI-issued key is needed to use the OpenAI SDK against that endpoint.

## 5. Live generated-code and tracing acceptance

1. Supply funded provider credentials and working Langfuse project credentials.
   Use a small synthetic dataset and a limited test key. Confirm Langfuse
   authentication with the project's configured client; absence of an exception
   from inference alone does not prove trace delivery.
2. With the verification owner, explicitly set `llm.generator: llm`, keep the
   approved provider, and set the validated model identifier in
   `configs/verification.yaml`. Do not alter statistical thresholds for this check.
3. Rebuild/recreate both API and worker so the verification configurations match.
   A different configuration digest must fail closed.
4. Run `scripts/check_workflow_stack.py` again. Inspect the actual stored
   `falsification_code`, executed statistics, p-values, q-values, effect sizes and
   final verdicts. Preserve the exact generated source and logged seed for replay.
5. Confirm generation happens in the trusted API process. The worker consumes
   prepared source through the gateway hook and never calls the external model.
   Keep worker public egress disabled. The whole tested batch gets one BH correction.
6. Confirm the Langfuse trace uses the run's UUID-derived trace ID and contains
   workflow stages and the falsification-generation observations with insight IDs.
   The existing generator tracing is best-effort, so visually confirm delivery.
7. Test missing/invalid key, provider rejection, malformed generated Python and
   unavailable provider. Expect recorded generation failure/NOT_TESTABLE or a
   degraded run, never template substitution, a false PASS or memory write.
8. Record evidence in the checklist below. Restore explicit template mode when
   returning to offline tests; never report a template result as a model result.

Worker-side Langfuse export is disabled in Compose. A bounded completion relay now
uses validated Redis task results to export counts and up to 50 insight ID/outcome
rows from the trusted graph, under the run trace. It omits prompts, source, raw rows
and exception text. Local executor logs still carry detail; a killed task has no
completion result and is represented by the caller's failure observation. Accept
remote relay delivery with credentials; never enable public worker egress.

## Tester sign-off

- [ ] Record checkout commit, dependency branch status, OS and package versions.
- [ ] Reproduce the keyless suite and record the actual pass/fail counts.
- [x] Complete live Docker upload, Celery execution and Chroma persistence.
- [x] Confirm real MiniLM embedding and retrieval, not a test embedding.
- [x] Complete live worker-loss/timeout checks and automated incomplete-family refusal checks.
- [x] Complete actual Gemma proposal and fresh-verification checks.
- [ ] Complete actual DeepSeek generation and stored-source replay checks.
- [ ] Inspect Langfuse trace/run linkage; record the worker relay limitation.
- [ ] Record invalid-key/provider-failure outcomes and PASS-only memory evidence.
- [ ] Obtain verification-owner review before merging memory/sandbox integration.

For every live check record date, commit, mode, model, run/task IDs, expected and
actual behavior, artifact/log locations and pass/fail/deferred. Exclude credentials
and raw participant records. Upstream W1/W8 and the V1 floor decision are now
implemented; see the team checklist. Benchmark conclusions, full B/C evaluation,
dashboard episode controls and cloud acceptance remain owner work. Test realistic
Celery family sizes before deployment: the current 90-second task limit does not
establish readiness for 50 sequential tests and shadow comparisons.

## Follow-up live acceptance after pulling `2707af0`

- Rebuilt API and worker with explicit local Gemma analysis and template verification.
  Run `e1705647-c5c9-4748-80b3-2cfe6101ad61`: completed, 1 PASS, 1 REJECT,
  complete proofs and PASS-only memory, recorded in `artifacts/workflow_stack_smoke.json`.
- Real Redis/worker round trip using an explicit **synthetic** generator-outage fixture:
  run `2035d0d0-a6a5-4a79-b0f8-0e82631cc336` degraded, one retained REJECT proof
  with null p-value, generator-unavailable count 1 and zero memory writes.
  This tests outage transport, not a live paid-provider call.
- Shared client and bounded relay have fixture-based coverage. Actual inference,
  remote Langfuse export and replay acceptance remain with the credentialed tester.
