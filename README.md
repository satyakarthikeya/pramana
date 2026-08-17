# PRAMANA

**Self-evolving data analysis agent with execution-grounded verification.**

An LLM agent that analyses datasets and reports insights — but every insight must survive
actual code execution and statistical falsification before it reaches the user or long-term
memory. Nothing unverified passes the gate, so memory stays clean by construction.

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
    falsification/   DeepSeek V4 code generation
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
dataset → sub-agents (Gemma) → analysis agent → VERIFICATION GATEWAY (DeepSeek V4)
                                                  ├─ PASS → memory (ChromaDB) → report
                                                  └─ REJECT → discarded
```

The gateway generates falsification code, **executes** it (permutation / bootstrap),
applies Benjamini-Hochberg correction across the whole run, scores the evidence, and emits
a proof object per insight. Every reported insight ships with its proof.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on Linux/macOS
pip install -r requirements.txt
pip install -e .
cp .env.example .env               # then fill in your keys
pytest
```

Working on one module only? Install just what you need:
`pip install -r requirements/verification.txt -r requirements/dev.txt`

## Working agreement

- Edit your own folders; import everyone else's (`OWNERSHIP.md`).
- Import the contracts from `pramana.contracts` — never redefine them locally.
- Thresholds and seeds live in `configs/`, never in code.
- **The invariant:** `memory_write ⟹ verdict == PASS`. If a change would weaken it,
  stop and raise it instead of implementing it.

## Status

Skeleton. Modules are stubs carrying their owner, scope reference, and build-order
position; implementation follows each member's `SCOPE_*.md` build order.
