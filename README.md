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
dataset → preparation (rules; Gemma only where stuck) → analysis agent (LLM proposes claims)
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
.venv\Scripts\python.exe -m pramana
```

The last line is the **one start command**. Open **http://127.0.0.1:8080**.
On Linux/macOS, use `.venv/bin/python` instead. No Docker, Redis, Celery worker,
Ollama, Langfuse account, paid key or `.env` file is needed for this V1 profile.
Internet is needed for package installation and the first local MiniLM embedding
model download; allow that first-use download to finish. Memory persists locally.
If port 8080 is already used (for example by the Docker API), start with
`--port 8081` and visit that port. The app binds to loopback, not a public interface.

### Use V1

1. Click **Try the sample**, or upload CSV/XLSX and optionally enter a question.
   The sample is generated from a seeded recipe in the repository; no participant
   data is committed. The rule scan explores the supported relationships rather
   than promising free-form question answering.
2. Watch the stage and elapsed time. Inspect detected column roles, exclusions and
   the bounded cleaned-row preview. These are data descriptions, not findings.
3. Read **Verified findings**, then **Rejected claims / Not a finding**. Open the
   readable proof and its stored code; raw proof JSON remains available separately.
4. Download JSON or CSV results. Only proof-bearing claims are exported, with their
   PASS/REJECT labels; CSV cells are protected against spreadsheet formulas.
5. Browse/search verified memory. Start a second upload: relevant historical lessons
   appear as **hints to re-test**, not current findings. Each links to its source run.
6. **New analysis** resets the form; it does not cancel or silently restart an active
   statistical family. Only one run is allowed at a time.

### Optional model configuration

Copy `.env.example` to `.env` only if you need overrides. Never commit keys.
V1's launcher explicitly selects template verification by default, while the
standalone gateway configuration keeps the verification owner's LLM default.
For the approved DeepSeek code generator, set local `DEEPSEEK_API_KEY` and a matching
`DEEPSEEK_BASE_URL`, configure valid Langfuse tracing, and run:

```powershell
.venv\Scripts\python.exe -m pramana --generator llm
```

Missing credentials fail closed; they never trigger template substitution. Hosted
Gemma proposal (`PRAMANA_ANALYSIS_ENGINE=api`) is optional and not accepted against
a real funded provider in this V1 session. Configure `PRAMANA_ANALYSIS_API_KEY`,
the approved Gemma model and endpoint explicitly; see `configs/analysis.yaml`.
The rule proposer stays the shipped default. Existing non-V1 Docker tooling remains
available for development but is not a V1 startup dependency.

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
