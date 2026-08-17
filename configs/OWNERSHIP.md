# OWNERSHIP — `configs/`

One config file per module. Thresholds and seeds live **here and only here** —
hardcoding them in code is a rule violation, not a style preference (`AGENTS.md` §3.3).

| File | Owner | Holds |
|---|---|---|
| `verification.yaml` | P.P. Satya Karthikeya | alpha, evidence threshold, n_permutations, n_bootstrap, seed, executor limits, DeepSeek settings |
| `analysis.yaml` | P. Rohith | ingestion limits, cleaning, schema inference, hypothesis caps, benchmark rules |
| `runtime.yaml` | B. Karthikeya | graph timeouts/retries, Celery + Redis, Langfuse, logging |
| `memory.yaml` | M. Karthik Reddy | ChromaDB, retrieval, API settings |

## Rules

1. Edit only your own file. Need a value from someone else's? Ask them to expose it.
2. **No secrets in here.** API keys and credentials come from the environment —
   `.env` locally (gitignored), a secret manager in cloud. See `.env.example`.
3. Seeds are configurable and logged, so any run can be reproduced (`AGENTS.md` §3.4).
4. Changing `verification.yaml` changes what PASSes. Note the reason in the commit —
   the report needs a record of which thresholds produced which results.
