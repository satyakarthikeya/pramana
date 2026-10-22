# Orchestration integration contract

The graph is complete independently of teammate implementation timing. By default,
orchestration calls the public functions already exported by `pramana.analysis` through a
thin native adapter. This adapter loads, cleans, profiles and classifies the data, persists
the exact cleaned dataframe under `PRAMANA_DATA_DIR/runs/<run_id>/cleaned.pkl`, and generates
candidate insights against that same reference.

The three analysis environment handlers remain an all-or-none override for deployments that
want a separate analysis service. Memory and verification use their configured integration
boundaries. No teammate package imports `pramana.orchestration`.

Each function accepts one mapping and returns one mapping. Unknown or missing response keys
fail validation and degrade the run. The configured import path must remain inside its owned
package.

| Environment variable | Package | Required response |
|---|---|---|
| `PRAMANA_INGEST_HANDLER` (optional override) | `pramana.analysis` | `dataset`, `dataset_ref` |
| `PRAMANA_PREPARATION_HANDLER` (optional override) | `pramana.analysis` | `dataset`, `dataset_ref`, `schema_profile` |
| `PRAMANA_ANALYSIS_HANDLER` (optional override) | `pramana.analysis` | `candidate_insights` |
| `PRAMANA_MEMORY_HANDLER` (optional override) | `pramana.memory` | `memory_receipts` |
| `PRAMANA_VERIFICATION_HANDLER` (optional override) | `pramana.verification` | `proof_objects` |

Example handler-override configuration:

```text
PRAMANA_INGEST_HANDLER=pramana.analysis.public:ingest
PRAMANA_PREPARATION_HANDLER=pramana.analysis.public:prepare
PRAMANA_ANALYSIS_HANDLER=pramana.analysis.public:analyze
PRAMANA_MEMORY_HANDLER=pramana.memory.public:write_verified
PRAMANA_VERIFICATION_HANDLER=pramana.verification.public:verify_request
```

Do not configure only one or two analysis overrides. Orchestration rejects partial
configuration rather than mixing two potentially incompatible analysis implementations in
one run.

## Analysis requests

`ingest` receives `run_id` and the uploaded `dataset_ref`. It returns the loaded dataset and
a non-empty reference for those exact values.

`prepare` receives `run_id`, `dataset`, and `dataset_ref`. It returns the cleaned dataset, a
worker-visible reference to the cleaned values, and a schema-profile mapping. Candidate
generation and verification must use this same cleaned artifact.

`analyze` receives `run_id`, the cleaned `dataset`, its `dataset_ref`, and `schema_profile`.
It also receives the optional `user_query` supplied with the run. It returns
`candidate_insights`, each valid under `pramana.contracts.CandidateInsight`, with a unique ID
and the exact cleaned `dataset_ref`. These are proposals only; analysis never sets PASS or
REJECT.

## Verification and memory

The graph sends the complete candidate family to one Celery verification task so BH-FDR can
be applied once across the run. The task handler receives `run_id`, `dataset_ref`, and
`candidate_insights`, and returns one complete proof per candidate.

The memory handler receives `run_id`, `dataset_ref`, `candidate_insights`,
`schema_profile`, and PASS-only `proof_objects`. Orchestration
constructs that request only from exact `Verdict.PASS` objects. The memory package must still
apply its own verification-owned guard before ChromaDB writes; defence in depth is required.

The user report is built inside orchestration from the original candidate claim and exact
gateway-issued PASS proof, so no external formatter can replace or forge either field.

## Calling the completed workflow

With no memory override, orchestration uses the memory owner's `ChromaLessonStore`
and supplies original candidates and a schema fingerprint. Backend failures degrade
the run; they never select the temporary JSONL store. A deployment may explicitly
choose `pramana.memory.store:write_verified` for that legacy backend.

An API caller needs one entrypoint. The three
analysis variables may be omitted to use the native adapter. The verification variable may
also be omitted: the Celery worker then loads only the exact
`PRAMANA_DATA_DIR/runs/<run_id>/cleaned.pkl` artifact and invokes the verification gateway's
batch function directly.

When the verification configuration explicitly selects `llm`, the trusted process
generates programs before queueing. The worker receives a validated prepared batch,
checks the candidate/config binding and supplies the programs through the gateway's
`generate=` hook. Failed generations become NOT_TESTABLE through the normal gateway
logic. There is no worker-side API call or template substitution.

```python
from pramana.orchestration import run_configured_workflow

final_state = run_configured_workflow(
    "/data/pramana/run-123/upload.csv",
    user_query="Which health measurements vary with age?",
)
```

For live intermediate results, construct the configured graph and consume validated states:

```python
from pramana.orchestration import build_graph, configured_adapters, new_run, stream_graph

state = new_run("/data/pramana/run-123/upload.csv", user_query="Find useful patterns")
graph = build_graph(configured_adapters())
for snapshot in stream_graph(state, graph):
    print(snapshot.visited_nodes, snapshot.status)
```

## Episode runs

Use `new_run(..., episode_mode=True)` or
`run_configured_workflow(..., episode_mode=True)` to retrieve prior verified lessons
after preparing the current schema and before proposing candidates. The native
proposer receives `run_id`, `user_query`, and `lesson_hints`. Handler overrides also
receive `lesson_hints` in `AnalysisRequest`. A deterministic proposer may ignore
hints; the explicitly selected DeepSeek proposer can use them to suggest claims.

Historical proofs remain under `retrieved_lessons` for source provenance. They never
populate the current run's `proof_objects`. Every new candidate enters the current
verification family. A retrieval failure degrades the episode before analysis.
Batch mode clears historical hints and does not connect to memory until a PASS write.

For a shared store instance, pass
`configured_adapters(memory=MemoryIntegration(store), ...)`. The API's existing
custom memory writer remains supported. Its upload endpoint currently starts batch
runs; exposing an episode toggle there is an API-owner follow-up.
