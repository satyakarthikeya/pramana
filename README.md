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
