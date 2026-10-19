# PRAMANA development stack

From the repository root:

```powershell
Copy-Item .env.example .env
docker compose -f docker/docker-compose.yml up --build
```

The API container joins separate internal queue and storage networks plus an egress network.
The API image pins Chroma's client to 1.5.9 and Compose uses that same server release.
Compose explicitly selects HTTP Chroma and Celery verification, so writes reach the
shared storage service instead of creating an ephemeral local index in the API container.
To activate the installed Gemma proposer explicitly, set `PRAMANA_ANALYSIS_ENGINE=ollama`
before starting Compose. The API uses `host.docker.internal:11434` to reach host Ollama.
`PRAMANA_ANALYSIS_MODEL` defaults to `gemma2:2b`; the analysis owner's validated model
settings still refuse non-Gemma tags and non-local endpoints.
The worker joins only the queue network, so it can reach Redis but cannot reach ChromaDB or
the public internet. It also runs as a non-root user with a read-only filesystem, dropped
Linux capabilities, process/CPU/memory limits, and a bounded temporary directory.
Uploaded run data is shared from the API to the worker through a dedicated volume that is
read-only in the worker. Both images create that mount point with the same non-root owner,
and the orchestration dependencies include `pyarrow` so the worker can deserialize dataframe
artifacts produced by the API image.

Generated-code import, filesystem, and subprocess policy remains owned by
`pramana.verification.executor`. Container restrictions are an additional boundary, not a
replacement for that policy.

The worker uses the repository's native verification gateway by default. An alternate
verification implementation can be configured as a trusted import path:

```text
PRAMANA_VERIFICATION_HANDLER=pramana.verification.<module>:<function>
```

The handler receives one mapping containing `run_id`, `dataset_ref`, and the complete
`candidate_insights` family. It must return a mapping containing `proof_objects`.

The worker deliberately has no public egress because it executes untrusted generated code.
The default `llm.generator: template` works offline. With `generator: llm`, the Celery
adapter calls the verification owner's generator in the trusted API process. It queues
the checked source (or explicit generation failure) with the entire candidate family.
The worker uses the gateway's existing `generate=` hook to execute that exact source,
then applies BH-FDR once. Candidate payloads and a configuration digest must match.
The worker refuses an LLM batch without trusted prepared programs. It never calls
DeepSeek or silently switches to templates. Worker-side Langfuse delivery remains
unavailable without a bounded telemetry relay; the trusted generation spans and graph
stages share the run trace. Do not add public egress to the execution worker.
