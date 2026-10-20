# Workflow integration handoff, 20 October 2026

API keys are not required to complete the workflow implementation. The user has
explicitly deferred paid-provider and live Langfuse checks to the tester. See
[TESTING_PHASE.md](../team/TESTING_PHASE.md) for setup, credentials, exact commands, expected
failure behavior and the tester sign-off checklist. Implementation readiness and
live-service acceptance are tracked separately.

For the audited goals of all four members, including incomplete work, see
[TEAM_GOALS_CHECKLIST.md](../team/TEAM_GOALS_CHECKLIST.md). Working workflow integration
does not mean every architecture goal is closed: W4's shared inference client and
the isolated-worker telemetry relay remain implementation work, not merely missing
credentials.

This work builds on `origin/feat/rohith/memory-backend` (memory/API/dashboard)
and `origin/feat/rohith/llm-claim-proposer` (Gemma proposer). Both are dependencies,
not newly authored modules. Merge those dependencies before this integration PR.
Main is unchanged. Only orchestration, its tests, Docker, a smoke-check script and this handoff receive
new implementation changes.

## Implemented in the integration branch

- Native analysis forwards the question, run ID and historical hints to the
  analysis owner's configured proposer. Explicit offline and Ollama modes remain
  distinct; a missing model never causes silent substitution.
- Native guarded Chroma writes receive original candidates, their cleaned
  dataset reference, schema fingerprint and PASS proofs. No handler environment
  variable is required for the standard store. Legacy handlers stay explicit.
- Episode runs retrieve source-verified historical hints after schema preparation.
  New claims require new verification. Retrieval failures degrade the run.
- Mapping memory overrides also receive candidate/schema context. Analysis
  overrides receive historical hints.
- Graph stages create Langfuse observations under the run trace when configured.
- In LLM queue mode, falsification generation runs in the trusted process. Prepared
  source or explicit generation failures reach the isolated worker through the
  gateway's public generator hook. The complete family and config digest must match;
  the worker does not call DeepSeek. Statistics and verdicts remain gateway-owned.
- Compose selects HTTP Chroma and Celery explicitly. API client and Chroma server
  both use 1.5.9. The verification worker keeps its existing isolation.

## Acceptance checks

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/orchestration tests/integration/test_episode_workflow.py
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe scripts/check_workflow_stack.py
```

The episode integration test uses real analysis, the real template gateway with
subprocess execution and BH correction, and persistent Chroma. It explicitly
injects a small test embedding to avoid a model download. This proves storage and
workflow behavior; it does not establish live Gemma, DeepSeek or Langfuse service
availability. Existing API tests cover upload through the graph to guarded memory.

Validated locally: full suite **563 passed** after runtime fixes, with 10 existing
collection/deprecation warnings. Repository lint passed. Mypy passed for orchestration,
common and the stack smoke script (23 source files). `pip check` and Docker Compose
configuration validation passed. No verification threshold or proof contract changed.

The initial full-suite attempt ran before missing analysis/API dependencies were
installed. The final successful run above supersedes that result. The native
analysis integration test now uses the production graph budget instead of the
30-second unit-test budget because five real resampling tests take about 42 seconds
on this machine. Real timeout/fail-closed tests remain enabled and passing.

## Live keyless acceptance

Docker baseline and actual Gemma API runs passed through Redis, the isolated worker,
real statistical execution, MiniLM embeddings and guarded HTTP Chroma persistence.
The Gemma API run produced 1 PASS and 1 REJECT. Existing lessons survived Chroma
recreation and remained searchable. Worker termination and failed-execution tests
both produced degraded runs without memory writes. Run IDs and evidence locations
are in [TESTING_PHASE.md](../team/TESTING_PHASE.md).

Runtime fixes: numerical thread caps in the worker image keep imports below the
unchanged execution-memory limit; exhausted execution failures now degrade the
graph; Chroma's named volume now mounts at the actual `/data` database path.

## Remaining deployment/owner dependencies

- W4's shared OpenAI-compatible inference client is not implemented. Existing
  module-specific callers need a coordinated migration; the shared Langfuse
  client alone does not satisfy W4.
- Docker Desktop runs from the user's AppData Programs/DockerDesktop directory.
  Keyless Compose/Redis/worker-kill acceptance passed on this machine.
- Worker Langfuse delivery needs a bounded telemetry relay. Trusted API generation
  and graph observations have network access, but worker isolation stays intact.
- Gemma/Ollama, DeepSeek and Langfuse need their live services and local credentials
  for live activation. No secrets belong in commits or PR descriptions.
- The API currently starts batch runs. An episode control belongs to the API owner;
  the graph entrypoint already supports it without API changes.
- Verification calibration, claim-column enforcement and evaluation results remain
  verification-owner work. Workflow integration does not establish their completion.
- Memory safety and sandbox-related changes require Satya's review before merge.

No claim of whole-project completion follows from passing the offline tests.
