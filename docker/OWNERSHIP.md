# OWNERSHIP — `docker/`

**Docker is tooling, not a person's module.** Nobody "owns Docker" (`SCOPE.md` §3).
The split is:

| Concern | Who |
|---|---|
| Base images + `docker-compose.yml` for the dev stack | B. Karthikeya |
| Deploying that same stack to cloud, volumes, secrets | M. Karthik Reddy |
| Sandbox constraints the executor container must satisfy | P.P. Satya Karthikeya (specifies only — see `verification/executor/policy.py`) |

Treat it like any shared dependency: coordinate before changing something others build on.

## Expected contents

| File | Purpose |
|---|---|
| `Dockerfile.api` | FastAPI app image |
| `Dockerfile.worker` | Celery worker image — runs falsification code, so it carries the sandbox limits |
| `docker-compose.yml` | dev stack: api + worker + redis + chromadb |
| `docker-compose.prod.yml` | cloud overrides: persistent volumes, secrets, resource caps |

Not written yet — these are B. Karthikeya's build-order step 3.

## Non-negotiable for the worker image

The executor container runs untrusted LLM-generated code (`AGENTS.md` §4):

- no network access
- no writes outside a temp dir
- memory and CPU caps
- hard timeout, enforced outside the executed process

If the container can't enforce these, the executor can't be considered sandboxed and the
gateway's safety claim doesn't hold.

## Secrets

Never baked into an image or committed. `DEEPSEEK_API_KEY` and Langfuse keys are injected
at runtime from the environment or the cloud secret manager.
