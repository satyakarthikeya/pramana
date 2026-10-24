# Memory, API and dashboard: local work by Rohith covering Karthik Reddy

Local implementation on `feat/rohith/memory-backend`, based on the shared main
baseline. Requested by Rohith while Karthik Reddy is unavailable. Rohith authorized
local commits on 19 October 2026; publishing remains a separate step. Existing Rohith PRs remain on
their original branches; this branch does not incorporate unmerged PRs #13-17.

## Implemented

- `memory/lesson.py`, `abstraction.py`, `fingerprint.py`: deterministic historical
  lessons tied to the real candidate, source reference, schema, run and full proof.
  No model calls, participant rows or reconstruction of missing claim text.
- `memory/store.py`: persistent or HTTP ChromaDB, configured all-MiniLM-L6-v2
  embeddings and cosine search, whole-batch guard admission before embedding or
  writing, idempotent retries and conflict refusal. Revalidate every retrieved
  lesson and its proof. A corrupt record causes an error, not an accepted finding.
- `memory/retrieval.py`: verified historical hints for another dataset, optionally
  excluding the current source run. Hints never carry a verdict for a new dataset.
- `api/`: bounded CSV/XLSX uploads, asynchronous local background graph execution,
  status, results and read-only memory browse/search. SQLite retains metadata and
  results; interrupted runs fail on restart and are not silently re-executed.
- `dashboard/static/`: upload, recent runs, separate PASS findings and rejected
  claims, original proof inspection, and memory browse/search. Dynamic text uses
  textContent, not HTML interpolation. No unproved candidate text is published.
- The API's memory adapter gets claim and schema context from the existing graph
  hook; it does not change shared contracts or graph internals. Verification still
  receives the complete candidate family once and owns all statistics/verdicts.

The existing proof-only JSONL handler is retained for existing CLI integrations
and tests. It remains a distinct temporary backend; it is never selected as a
fallback for a failed Chroma operation. The new API uses ChromaLessonStore.

## Run locally

Install the existing requirements (no new package was added). From the repository root:

```powershell
$env:PRAMANA_API_VERIFICATION_MODE = "inprocess"
$env:PRAMANA_CHROMA_MODE = "persistent"
.venv/Scripts/python.exe -m uvicorn pramana.api.main:app --host 127.0.0.1 --port 8080 --workers 1
```

Open http://127.0.0.1:8080 . The explicit inprocess setting avoids Redis locally;
falsification still executes through the gateway's real subprocess sandbox. The
verification generator remains whatever configs/verification.yaml explicitly selects
(currently template); no silent model substitution. Local verification does not
establish that Celery/Docker/cloud activation has been tested.

By default the API selects Celery verification, as configured in configs/memory.yaml.
For compose, select PRAMANA_CHROMA_MODE=http to use CHROMA_HOST/CHROMA_PORT instead
of a local persistent client. Use a compatible Chroma client/server release; the
existing compose image is 0.5.23, while this local environment uses client 1.5.9.
Do not claim those versions interoperable without a deployment check.

API endpoints:

| Method | Path | Purpose |
|---|---|---|
| POST | /api/runs | Multipart file and optional user_query; returns 202 + run UUID |
| GET | /api/runs | Bounded recent run list |
| GET | /api/runs/{run_id} | Status and sanitized failure information |
| GET | /api/runs/{run_id}/results | Verified findings and separately labelled rejected claims |
| GET | /api/memory | Bounded verified historical lesson browse |
| POST | /api/memory/search | Read-only semantic query and bounded top_k |
| GET | /health | API liveness only, not dependency readiness |

SQLite is under data/api/, uploaded files under data/api/uploads/, and local
Chroma storage under data/memory/chroma/. The real embedding model is cached under
the storage directory's sibling models/all-MiniLM-L6-v2/. All are ignored by Git.
Initial embedding use downloads the configured model; missing/network failures
propagate. Test embeddings are explicitly injected by tests, never chosen by config.

The current runner uses FastAPI's in-process background task and one API worker,
with configured max_active_runs. It is a local/private prototype, not a distributed
job scheduler. A server restart marks outstanding jobs failed. Persist completed
results before process shutdown and start new runs explicitly for interrupted work.

## Inputs and integration still needed

1. **B. Karthikeya:** coordinate extending the standard proof-only memory handler
   payload with candidate/schema context, and an episode-hint input for the analysis
   stage. The new API already stores contextual lessons through an existing adapter,
   but automatic retrieval and use in a future graph run are not implemented here.
2. **Cloud/deployment owner:** choose a provider, account, domain, persistent data
   location and access policy. Then configure compatible Chroma client/server
   versions, private networking, TLS/access control and actual Celery connectivity.
   No cloud account resources, costs or deployments were created in this work.
3. **Langfuse admin:** credentials are needed only for live traced LLM activation.
   Rule-based abstraction and MiniLM embeddings do not call Gemma/DeepSeek.
4. **Satya:** review memory safety before any merge. The guard itself is unchanged;
   this code invokes it before every admitted write and revalidates stored proofs.

Shared-file changes to review later: PROJECT.md status cells, pyproject.toml's
dashboard package assets, and analysis-independent configs/memory.yaml settings.
No dependency changes; no verification thresholds, FDR, sandbox or shared proof
contracts were changed. File ownership remains Karthik Reddy's; the work is local
coverage by Rohith and does not reassign ownership or impersonate Karthik.

## Verification

```powershell
python -m pytest tests/unit/memory tests/unit/api -q -o addopts=--strict-markers --tb=short
python -m pytest -q -o addopts=--strict-markers --tb=short
python -m ruff check .
python -m mypy src/pramana/memory src/pramana/api scripts/check_verified_memory.py --python-version 3.13
node --check src/pramana/dashboard/static/app.js
python scripts/check_verified_memory.py
```

The focused tests include a real persistent Chroma index with an explicit test
embedding, plus an upload through the actual graph, analysis, real template
gateway, sandbox, BH correction, guarded memory, API results and search. The real
model smoke script separately checks the configured MiniLM embedding and persistent
retrieval using a synthetic claim that must first PASS the actual gateway.
Browser interaction and cloud deployment are separate checks; HTTP/static-file
tests alone do not establish that every browser interaction was exercised.

Actual local checks on 18 October 2026:

- Full suite: **506 passed**, 10 warnings (existing enum collection warnings and
  dependency/test-embedding deprecations), 194.46 seconds.
- Focused memory/API tests: **18 passed**, including the real graph/gateway path.
- Repository ruff, memory/API/smoke-script mypy and JavaScript syntax: passed.
- Wheel built; inspected archive contains dashboard index.html, style.css and app.js.
- Real configured MiniLM model downloaded and used: the smoke claim passed the
  actual template gateway with seed 20260817 and 10,000 permutations; reopening
  persistent Chroma storage retrieved that lesson. Report stays in ignored
  artifacts/verified_memory_smoke.json; the smoke index contains synthetic data only.
- Headless Chrome rendered the dashboard; screenshot inspected at ignored
  artifacts/dashboard-memory.png. Complete browser upload/search interactions
  were not automated; those endpoints and their graph integration were tested above.

The original implementation was left uncommitted as requested. Local commits were
subsequently authorized by Rohith on 19 October 2026. No push, PR or cloud deployment
is included in that commit request.

Pre-commit recheck on 19 October 2026: focused memory/API tests **18 passed**;
full suite **506 passed**, 10 warnings, 204.11 seconds. Repository lint,
memory/API type checks, JavaScript syntax and diff checks passed again.
