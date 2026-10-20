# Workflow integration handoff, 20 October 2026

API keys are not required to complete the workflow implementation. The user has
explicitly deferred paid-provider and live Langfuse checks to the tester. See
[TESTING_PHASE.md](TESTING_PHASE.md) for setup, credentials, exact commands, expected
failure behavior and the tester sign-off checklist. Implementation readiness and
live-service acceptance are tracked separately.

For the current goals of all four members, see
[TEAM_GOALS_CHECKLIST.md](TEAM_GOALS_CHECKLIST.md). The follow-up branch from
`origin/main` `2707af0` adds W4's shared inference interface and bounded completion
telemetry relay. Existing module callers still need owner-reviewed migration;
remote Langfuse delivery and realistic batch timeout budgets need acceptance.

The original workflow PR #20 and its memory/API and Gemma proposer prerequisites
are now merged. The follow-up builds from current main, not those old dependency
branches. Changes remain in common/orchestration, their tests, shared integration
tests, local Docker and handoff documentation; no teammate module internals changed.

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

Validated locally after pulling gateway PR #21: full suite **747 passed** in
387.80 seconds, with 10 existing
collection/deprecation warnings. Repository lint passed. Mypy passed for orchestration,
common and the stack smoke script (25 source files). `pip check` and Docker Compose
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
are in [TESTING_PHASE.md](TESTING_PHASE.md).

Runtime fixes: numerical thread caps in the worker image keep imports below the
unchanged execution-memory limit; exhausted execution failures now degrade the
graph; Chroma's named volume now mounts at the actual `/data` database path.

## Remaining deployment/owner dependencies

- W4's additive interface is implemented in `common/llm_client.py`. Consumer
  consolidation remains a coordinated owner task; see [client handoff](SHARED_LLM_CLIENT.md).
- Docker Desktop runs from the user's AppData Programs/DockerDesktop directory.
  Keyless Compose/Redis/worker-kill acceptance passed on this machine.
- A bounded completion relay now exports validated result metadata from the trusted
  graph, not from the worker. Actual Langfuse delivery is untested without credentials;
  this does not replay every executor log. Worker isolation stays intact.
- Gemma/Ollama, DeepSeek and Langfuse need their live services and local credentials
  for live activation. No secrets belong in commits or PR descriptions.
- The API currently starts batch runs. An episode control belongs to the API owner;
  the graph entrypoint already supports it without API changes.
- Upstream now includes W1/W8, a V1 floor decision and evaluation A/D. The full
  benchmark study, B/C and measured deployment budgets remain unfinished; workflow
  integration does not establish those results.
- Memory safety and sandbox-related changes require Satya's review before merge.

No claim of whole-project completion follows from passing the offline tests.
