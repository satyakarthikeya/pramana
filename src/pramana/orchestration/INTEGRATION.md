# Orchestration integration contract

The graph is complete independently of teammate implementation timing. Teammate packages
plug in through four environment-configured public functions; no teammate package imports
`pramana.orchestration`.

Each function accepts one mapping and returns one mapping. Unknown or missing response keys
fail validation and degrade the run. The configured import path must remain inside its owned
package.

| Environment variable | Package | Required response |
|---|---|---|
| `PRAMANA_INGEST_HANDLER` | `pramana.analysis` | `dataset`, `dataset_ref` |
| `PRAMANA_PREPARATION_HANDLER` | `pramana.analysis` | `dataset`, `dataset_ref`, `schema_profile` |
| `PRAMANA_ANALYSIS_HANDLER` | `pramana.analysis` | `candidate_insights` |
| `PRAMANA_MEMORY_HANDLER` | `pramana.memory` | `memory_receipts` |
| `PRAMANA_VERIFICATION_HANDLER` | `pramana.verification` | `proof_objects` |

Example configuration:

```text
PRAMANA_INGEST_HANDLER=pramana.analysis.public:ingest
PRAMANA_PREPARATION_HANDLER=pramana.analysis.public:prepare
PRAMANA_ANALYSIS_HANDLER=pramana.analysis.public:analyze
PRAMANA_MEMORY_HANDLER=pramana.memory.public:write_verified
PRAMANA_VERIFICATION_HANDLER=pramana.verification.public:verify_request
```

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

The memory handler receives `run_id`, `dataset_ref`, and `proof_objects`. Orchestration
constructs that request only from exact `Verdict.PASS` objects. The memory package must still
apply its own verification-owned guard before ChromaDB writes; defence in depth is required.

The user report is built inside orchestration from the original candidate claim and exact
gateway-issued PASS proof, so no external formatter can replace or forge either field.

## Calling the completed workflow

Once the five handler variables are configured, an API caller needs one entrypoint:

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
