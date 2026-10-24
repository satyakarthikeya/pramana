# PRAMANA development stack

From the repository root:

```powershell
Copy-Item .env.example .env
docker compose -f docker/docker-compose.yml up --build
```

The API container joins separate internal queue and storage networks plus an egress network.
The API image pins Chroma's client to 1.5.9 and Compose uses that same server release.
Compose explicitly selects HTTP Chroma and in-process verification, so writes reach the
shared storage service instead of creating an ephemeral local index in the API container.
Chroma 1.5 stores its database under `/data`; the named volume mounts at that exact
path. The older `/chroma/chroma` mount and `PERSIST_DIRECTORY` settings do not
configure persistence for this server image.
Both model roles use the official DeepSeek API with the same local `.env` key.
Gemma/Ollama is not used. Fill Langfuse credentials as well. The default in-process
profile matches the local V1 website. For the isolated queue path explicitly set
`PRAMANA_API_VERIFICATION_MODE=celery`; the generation/execution split below applies.
The worker joins only the queue network, so it can reach Redis but cannot reach ChromaDB or
the public internet. It also runs as a non-root user with a read-only filesystem, dropped
Linux capabilities, process/CPU/memory limits, and a bounded temporary directory.
The worker image installs a Python startup hook that caps numerical thread pools
at one thread in both the Celery process and sanitized executor children. This
avoids large BLAS virtual-memory reservations before tests start. The configured
1 GB execution limit and container restrictions remain enforced.
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
The project default is `llm.generator: template` (`configs/verification.yaml`). On this branch the Compose file
selects `llm` by default through `PRAMANA_VERIFICATION_GENERATOR` (the live DeepSeek profile); `fix/satya/report-polish` changes that default to `template`.
For explicit keyless acceptance, set `$env:PRAMANA_VERIFICATION_GENERATOR = "template"` before starting Compose;
that override is passed to both API and worker. With `generator: llm`, the Celery
adapter calls the verification owner's generator in the trusted API process. It queues
the checked source (or explicit generation failure) with the entire candidate family.
The worker uses the gateway's existing `generate=` hook to execute that exact source,
then applies BH-FDR once. Candidate payloads and a configuration digest must match.
The worker refuses an LLM batch without trusted prepared programs. It never calls
DeepSeek or silently switches to templates. The worker's Langfuse export is disabled:
its validated batch summary returns with proofs through Redis. The trusted graph
relays bounded completion metadata under the run trace (up to 50 insight IDs/outcomes;
no source, prompts, raw rows or exception text). This is not replay of every executor
log, and real remote delivery still needs tester credentials. Do not add public
egress to the worker. Large families may exceed the current 90-second Celery task
limit; size and measure production runtime budgets before benchmark-scale deployment.
