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
read-only in the worker.

Generated-code import, filesystem, and subprocess policy remains owned by
`pramana.verification.executor`. Container restrictions are an additional boundary, not a
replacement for that policy.

The stack will become runnable when the teammate-owned `pramana.api.main:app` and
verification task handler are implemented. Configure the latter as a trusted import path:

```text
PRAMANA_VERIFICATION_HANDLER=pramana.verification.<module>:<function>
```

The handler receives one mapping containing `run_id`, `dataset_ref`, and the complete
`candidate_insights` family. It must return a mapping containing `proof_objects`.
