# PRAMANA

**Data analysis agent with execution-grounded verification.**

1. **What it is:** upload a table; PRAMANA proposes relationships, runs the statistical tests as code, and sends each claim through the verification gateway, which issues PASS or REJECT with a proof object. Rejected claims are listed with the reason. Only PASS findings enter local memory, and memory offers them later as hints to re-test, never as findings.
2. **Three evidence levels:** *Exact* (arithmetic on your table, recomputed by code), *Measured* (a model scored on data it did not see) and *Tested* (passed the verification gateway). Exact and Tested are built; see `docs/ANALYST_LAYER_STATUS.md` for how far Measured has got.
3. **Run it:** `python -m pramana` after the Setup steps below, then open http://127.0.0.1:8080. The live profile needs a DeepSeek API key and Langfuse credentials in `.env`; the first run downloads a local embedding model (about 79 MB) used only for memory search.
4. **Test it:** `python -m pytest` (the full suite takes a while). Count: `python -m pytest --collect-only -q | tail -1`.
5. **Docs:** [docs/README.md](docs/README.md) is the index, [STATUS.md](STATUS.md) is the current state, [PROJECT.md](PROJECT.md) the architecture, [SCOPE.md](SCOPE.md) the scope and [AGENTS.md](AGENTS.md) the rules.

The default claim proposer is `api` (DeepSeek, from column summaries) and the default test generator is `template`. The offline profile (rule scan plus templates) needs no model API key; model-written test code is an explicit opt-in, never a silent fallback.

Capstone project, Team AB-07, Amrita School of AI. Supervisor: Rayappa David Amar Raj.

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
    falsification/   test generation: vetted templates (default), or DeepSeek-written code
    executor/        sandboxed runner + policy
    fdr.py, evidence.py, gateway.py, memory_guard.py
  memory/          ChromaDB verified lessons, guarded write path          [Karthik Reddy]
  api/             FastAPI backend                                        [Karthik Reddy]
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
dataset → preparation (rules) → proposer (model or rule scan proposes claims)
        → VERIFICATION GATEWAY (code renders the test, or DeepSeek writes it; our code decides)
              ├─ PASS → memory (ChromaDB) → report
              └─ REJECT → discarded
```

Models propose; code decides. In the gateway the default is a vetted test rendered by code per
claim type; with `--generator llm`, DeepSeek writes a falsification program that may only call
our vetted statistics library. The program is **executed** in a sandbox (permutation test),
Benjamini-Hochberg correction runs once across the whole run, and a deterministic gate issues PASS or REJECT with a proof object per
insight. No model produces a statistic or a verdict. Every verdict ships with its
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
model download (about 79 MB); allow that first-use download to finish. Memory persists locally.
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
| `deterministic` | Rule scan over every eligible column pair (offline) | nothing |
| `api` (default) | A model proposes claims from column summaries only | DeepSeek key, Langfuse |
| `planner` | A model plans the analysis from the profile and column summaries; claim filters apply | DeepSeek key, Langfuse |
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

The default generator is `template` (a vetted test per claim type, rendered by code). The
command below opts in to `llm`, where DeepSeek writes each falsification test:

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

- PASS supports an association on this dataset, not causation. There is no clinical
  interpretation. Claims are confirmed on a seeded held-out split; the Skeptic flags
  possible confounders but does not adjust for them.
- Effect floors do not separate chance from truth; corrected significance matters.
  Small real effects can pass. Strength words label the configured metric bands.
- Categorical-versus-categorical claims are out of scope. Passing claims carry a
  bootstrap effect interval (descriptive only). Above 3,000 rows trend claims are
  dropped with a recorded reason, to avoid the quadratic Sen-slope cost; rows are never
  silently subsampled.
- One run at a time, at most eight candidate claims per V1 run. Tests use the
  configured 10,000 permutations and can take several minutes on a laptop.
- The LLM generator's refusal/disagreement rate at scale and the four-condition
  evaluation are not established V1 results.

See [STATUS.md](STATUS.md) for what is built and verified, and [docs/ROADMAP.md](docs/ROADMAP.md)
for what is next. [docs/V1.md](docs/V1.md) is the historical V1 checklist.

Working on one module only? Install just what you need:
`pip install -r requirements/verification.txt -r requirements/dev.txt`

## Working agreement

- Edit your own folders; import everyone else's (each `src/pramana/*/OWNERSHIP.md` names its owner).
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

## Contributing

`main` is protected; every change goes through a pull request from a branch named
`<type>/<owner>/<short-task>` (for example `fix/satya/executor-relative-imports`), with
Conventional Commit subjects. Run the targeted tests and the full suite before you push, and
fill in the PR description. The full rules, including review and merge, are in
[AGENTS.md](AGENTS.md) section 8. Changes that touch `memory_write => verdict == PASS`,
p-values, FDR correction or sandbox safety need the verification owner's approval.
