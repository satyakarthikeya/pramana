# PRAMANA development stack

From the repository root:

```powershell
Copy-Item .env.example .env
docker compose -f docker/docker-compose.yml up --build
```

The API container joins separate internal queue and storage networks plus an egress network.
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
The current default `llm.generator: template` therefore works offline. Before switching the
verification configuration to the DeepSeek generator, falsification-code generation and
Langfuse export must run in an egress-enabled trusted API/gateway process, with only the
generated program dispatched to the isolated execution worker. Do not add general egress to
the worker: that would also give generated code a network path and violate `AGENTS.md` section
4. Worker-side Langfuse delivery is consequently unavailable in the current topology; its
events must be emitted by the trusted gateway process or forwarded through a future bounded
telemetry channel.
