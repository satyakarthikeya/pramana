# PRAMANA

**Self-evolving data analysis agent with execution-grounded verification.**

V1 proposes relationships in uploaded tables, executes statistical tests, and reports
only findings that PASS verification. Each finding has a proof, and only PASS findings
enter local memory. The default rule scan and template tests need no model API key;
approved LLM proposal/code generation are explicit opt-ins, never silent fallbacks.

Capstone project, Team AB-07, Amrita School of AI. Supervisor: Rayappa David Amar Raj.

## Start here

| File | Read it for |
|---|---|
| `PROJECT.md` | what PRAMANA is, architecture, contracts, evaluation design |
| `AGENTS.md` | rules every contributor and AI coding agent must follow |
| `OWNERSHIP.md` | which folder belongs to whom |
| `SCOPE.md`, `scope/SCOPE_*.md` | what each member is building right now |

## Layout

```
src/pramana/
  contracts/       CandidateInsight, ProofObject — imported by everyone   [Satya]
  common/          config, logging, Langfuse client                       [B. Karthikeya]
  analysis/        ingestion → cleaning → candidate insights              [Rohith]
    hypotheses/      correlation / group-difference / trend strategies
    benchmark/       40-dataset curation + demo dataset
  verification/    THE GATEWAY                                            [Satya]
    stats/           permutation, bootstrap, effect size (the trust anchor)
    falsification/   test-code generation: DeepSeek V4, or templates (offline)
    executor/        sandboxed runner + policy
    fdr.py, evidence.py, gateway.py, memory_guard.py
  memory/          ChromaDB verified lessons, guarded write path          [Karthik Reddy]
  api/             FastAPI backend                                        [Karthik Reddy]
  dashboard/       run + demo visualisation                               [Karthik Reddy]
  orchestration/   LangGraph spine, Celery plumbing                       [B. Karthikeya]
  evaluation/      ablation harness (later work item)                     [Satya]

configs/           one YAML per module — all thresholds live here
requirements/      one file per module + shared base
tests/             mirrors src/ ownership
docker/            shared tooling (build: B. Karthikeya, deploy: Karthik Reddy)
data/              gitignored — datasets never enter the repo
```

Every folder above carries an `OWNERSHIP.md` naming its owner, its boundaries, and the
rules that apply inside it.

## Pipeline

```
dataset → preparation (rules) → analysis agent (LLM proposes claims)
        → VERIFICATION GATEWAY (DeepSeek writes the test; our code decides)
              ├─ PASS → memory (ChromaDB) → report
              └─ REJECT → discarded
```

Target design — models propose and write code; code decides. In the gateway, DeepSeek V4 writes a
falsification program that may only call our vetted statistics library. That program is
**executed** in a sandbox (permutation test), Benjamini-Hochberg correction runs once across
the whole run, and a deterministic gate issues PASS or REJECT with a proof object per
insight. No model produces a statistic or a verdict. Every reported insight ships with its
proof. See `PROJECT.md` §2 for the full flow and for which parts are built today.

## Setup

Python 3.11+ is required. From a clean clone on Windows:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -e .
# Copy .env.example only if .env does not already exist; preserve existing keys.
# Fill DEEPSEEK_API_KEY and Langfuse credentials in .env, then:
.venv\Scripts\python.exe -m pramana
```

The last line is the **one start command**. Open **http://127.0.0.1:8080** (run `npm run build` in `web/` first, see below).
On Linux/macOS, use `.venv/bin/python` instead. No Redis, Celery worker or
local generative model is needed. The live profile requires DeepSeek and Langfuse
credentials in the ignored `.env` file; no keys belong in browser JavaScript.
Internet is needed for package installation and the first local MiniLM embedding
model download; allow that first-use download to finish. Memory persists locally.
If port 8080 is already used (for example by the Docker API), start with
`--port 8081` and visit that port. The app binds to loopback, not a public interface.

### Run with Docker (recommended)

Docker runs the API, ChromaDB and the web UI together; nothing else is installed on your
machine. Copy `.env.example` to `.env` first (keep existing keys), then:

```bash
docker compose -f docker/docker-compose.yml up --build -d
```

Open **http://localhost:3000**. Without Langfuse keys the model-driven parts cannot run,
so use the offline profile (rule scan and built-in test templates, no model):

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.offline.yml up --build -d
```

The embedding model is baked into the API image, so a run never waits on a download.

### Accounts

The first screen is sign-in. On a new server, "Create the first account" appears; that
account also takes any datasets already stored. Passwords are stored only as salted
scrypt hashes, sessions are server-side behind an HttpOnly cookie, and each user sees only
their own datasets and runs. Verified memory is still shared between accounts for now.
Set `PRAMANA_ALLOW_SIGNUP=0` to close sign-up once your accounts exist.

### Use it

1. Add a dataset (CSV or XLSX). It is stored and profiled by code immediately: detected
   column types, a **Data reader** brief (what each column holds, missing codes, outliers,
   things worth checking) and charts of every analysable column. Nothing is analysed yet.
2. Press **Analyse**, optionally with a question. Watch the stages and elapsed time.
3. Read **Verified findings**, then **Not a finding** (rejected, with the reason). Each
   finding shows its chart; open the proof for the numbers, seed and the code that ran.
   **How these claims were found** states how many column pairs were looked at versus
   tested, because the correction covers only the tested ones.
4. Download JSON or CSV. Only proof-bearing claims are exported, with PASS/REJECT labels.
5. Verified memory lists what passed; on a later dataset relevant lessons appear as
   **hints to re-test**, never as findings.

### Analyst engines

`PRAMANA_ANALYSIS_ENGINE` chooses who proposes claims; the gateway tests every claim the
same way regardless.

| Engine | What it does | Needs |
|---|---|---|
| `deterministic` | Rule scan over every eligible column pair | nothing |
| `api` | A model proposes claims from column summaries only | DeepSeek key, Langfuse |
| `agent` | A model explores with tested tools and a bounded Python workspace, then proposes claims | DeepSeek key, Langfuse |

The agent never computes a number or writes a claim sentence, and its spending is capped by
hard budgets in `configs/analysis.yaml` (`workspace.agent`). Design and limits:
[docs/ANALYSIS_AGENT.md](docs/ANALYSIS_AGENT.md).

### Without Docker

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -e .
cd web; npm ci; npm run build; cd ..
.venv\Scripts\python.exe -m pramana
```

`python -m pramana` serves the built UI from `web/dist` on http://127.0.0.1:8080.

### DeepSeek-only model configuration

Create `.env` from `.env.example` only if it does not already exist. Never overwrite
existing keys. Both analysis and verification use `DEEPSEEK_API_KEY` and the official
`https://api.deepseek.com` endpoint. `DEEPSEEK_MODEL=deepseek-flash` sets both roles;
`deepseek-v4-pro` is the explicit alternative, never an automatic substitution.
Live calls require `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and
`PRAMANA_LANGFUSE_ENABLED=true`. All calls are traced under the workflow run ID.

```powershell
.venv\Scripts\python.exe -m pramana --generator llm
```

Missing credentials, tracing failures, malformed JSON and invalid generated code
fail closed; they never trigger another model or a template substitution. Statistical
tests, BH correction, verdicts and PASS-only memory writes remain deterministic code.
Schema inference, cleaning and lesson formatting also remain rule-based; their
optional refiner hook is not a hidden model call. MiniLM embeddings remain local for
memory search only. Gemma/Ollama is no longer an inference dependency.

For an explicitly labelled offline reference run, set
`PRAMANA_ANALYSIS_ENGINE=deterministic`, `PRAMANA_VERIFICATION_GENERATOR=template`
and `PRAMANA_LANGFUSE_ENABLED=false`. This is not DeepSeek acceptance evidence.
See [the DeepSeek migration/testing checklist](docs/team/DEEPSEEK_ONLY_TODO.md).

### Storage and reset

Uploads, cleaned artifacts, run metadata and Chroma memory are under ignored `data/`
(or the explicitly selected `PRAMANA_DATA_DIR`). To start fresh **without deleting
anything**, stop the app, choose a new ignored subdirectory, then start it again:

```powershell
$env:PRAMANA_DATA_DIR = Join-Path (Get-Location) 'data/v1-fresh'
.venv\Scripts\python.exe -m pramana
```

Return to the old location to recover its history. Keep raw datasets and local
databases out of Git. The app is a local, single-user prototype, not a hardened
internet-facing service; do not expose it publicly.

### Limitations

- PASS supports an association on this dataset, not causation. There is no confounder
  adjustment, held-out replication or clinical interpretation.
- Effect floors do not separate chance from truth; corrected significance matters.
  Small real effects can pass. Strength words label the configured metric bands.
- Categorical-versus-categorical claims and bootstrap confidence intervals are out
  of V1. Tables with a usable trend axis are refused above 3,000 rows to avoid the
  quadratic Sen-slope cost; rows are never silently subsampled.
- One run at a time, at most eight candidate claims per V1 run. Tests use the
  configured 10,000 permutations and can take several minutes on a laptop.
- The LLM generator's refusal/disagreement rate at scale and the four-condition
  evaluation are not established V1 results.

See [the V1 checklist](docs/V1.md) for evidence and tasks still awaiting people,
credentials, a second machine or required reviews. Do not infer whole-project
completion from the existence of the dashboard.

Working on one module only? Install just what you need:
`pip install -r requirements/verification.txt -r requirements/dev.txt`

## Working agreement

- Edit your own folders; import everyone else's (`OWNERSHIP.md`).
- Import the contracts from `pramana.contracts` — never redefine them locally.
- Thresholds and seeds live in `configs/`, never in code.
- **The invariant:** `memory_write ⟹ verdict == PASS`. If a change would weaken it,
  stop and raise it instead of implementing it.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
```

Tests explicitly select template verification and use labelled model/embedding
fixtures where appropriate. They are not proof of paid-provider availability.
