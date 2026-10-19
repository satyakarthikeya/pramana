# Testing phase: workflow integration

Owner of this handoff: B. Karthikeya, CB.AI.U4AID23109.
Prepared on 20 October 2026 for the tester taking over live service checks.

## Current completion boundary

The workflow implementation can be completed without API keys. The committed
default explicitly selects deterministic analysis and template verification.
This mode executes actual statistical tests and guards memory writes without
calling a paid model. It must not be described as a successful live LLM test.

The implementation is on `feat/b-karthikeya/workflow-completion`, with workflow
commit `884eb4a`. Its prerequisites are the published memory/API and Gemma proposer
branches, combined in dependency merge `ac53abd`. Those prerequisites need review
and integration before this workflow branch merges. Main has not been changed.

| Check | Recorded result |
|---|---|
| Full automated suite | 561 passed, 10 collection/deprecation warnings, 293.27 seconds |
| Repository Ruff lint | Passed |
| Mypy for orchestration, common and stack smoke script | Passed, 23 source files |
| Installed dependency consistency (`pip check`) | Passed |
| Docker Compose configuration validation | Passed |
| Real analysis, subprocess tests, BH-FDR and persistent Chroma in integration tests | Passed; explicitly injected test embeddings |
| Two-run retrieval and fresh verification | Passed; old proofs do not become current proofs |
| Prepared-code worker execution and model-generation failure handling | Passed with explicit test fixtures; no live provider call |
| Live Compose upload through Redis/worker/Chroma | Pending; image downloads were still running at handoff |
| Live Gemma proposer | Pending; configured model download was still running at handoff |
| Live MiniLM model download/embedding/search | Not established by the test-embedding integration tests |
| Live DeepSeek code generation | Deferred to tester; no API key supplied |
| Live Langfuse authentication and trace inspection | Deferred to tester; no credentials supplied |
| Live worker termination during execution | Pending |

Do not promote a pending row to passed simply because the process started.
Background downloads and smoke-check processes were started during development;
check their outcome rather than assuming they completed. Successful stack smoke
results appear in ignored `artifacts/workflow_stack_smoke.json`. Successful local
proposer checks write ignored `artifacts/llm_proposer_<run_id>.json` and a run audit
under `data/runs/<run_id>/analysis_proposer.json`. Inspect the run/model/trace backend
and timestamp before treating an existing artifact as evidence for this checkout.

## 1. Reproduce the keyless checks

Run these PowerShell commands from the repository root, using Python 3.11+:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest --tb=short
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy src/pramana/orchestration src/pramana/common scripts/check_workflow_stack.py
.venv/Scripts/python.exe -m pip check
```

Leave `configs/verification.yaml` with `llm.generator: template` for this phase.
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
`deepseek-v4` has NOT been validated against a funded account. Before live testing,
confirm an available verification model with the provider and verification owner.
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

Worker-side Langfuse export still needs a bounded telemetry relay because the
worker lacks public egress. Its local logs carry the run/task IDs. Treat full remote
worker tracing as pending until that relay is implemented and tested; never give
untrusted execution public egress to make tracing work.

## Tester sign-off

- [ ] Record checkout commit, dependency branch status, OS and package versions.
- [ ] Reproduce the keyless suite and record the actual pass/fail counts.
- [ ] Complete live Docker upload, Celery execution and Chroma persistence.
- [ ] Confirm real MiniLM embedding and retrieval, not a test embedding.
- [ ] Complete worker-loss, timeout and incomplete-family refusal checks.
- [ ] Complete actual Gemma proposal and fresh-verification checks.
- [ ] Complete actual DeepSeek generation and stored-source replay checks.
- [ ] Inspect Langfuse trace/run linkage; record the worker relay limitation.
- [ ] Record invalid-key/provider-failure outcomes and PASS-only memory evidence.
- [ ] Obtain verification-owner review before merging memory/sandbox integration.

For every live check record date, commit, mode, model, run/task IDs, expected and
actual behavior, artifact/log locations and pass/fail/deferred. Exclude credentials
and raw participant records. Verification threshold calibration, claim-column
enforcement, benchmark conclusions, the dashboard episode control and cloud
deployment remain their respective owners' work; these workflow tests do not
establish their completion.
