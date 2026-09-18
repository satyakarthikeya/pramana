# PRAMANA — Presentation Overview

> A presentation-ready summary of the current PRAMANA repository.
>
> **Important status note:** this document describes the architecture and the
> work currently present across the repository branches. Some orchestration
> work exists on a separate contributor branch and is not yet merged into
> `main`. Present completed modules as completed, and present the end-to-end
> gateway integration as work in progress.

## 1. Project in one sentence

**PRAMANA is a self-evolving data-analysis agent that does not trust an LLM's
statistical claim until executable falsification code tests it and a
verification gateway produces an auditable proof object.**

The name *Pramana* means valid proof/means of knowledge. The central promise is:

```text
memory_write  =>  verdict == PASS
```

An insight that fails verification is rejected and cannot poison long-term
memory.

## 2. Problem statement

Traditional LLM data-analysis systems have two dangerous failure modes:

1. **Insight hallucination:** the model describes a correlation or group
   difference that is not supported by the data.
2. **Memory poisoning:** an unverified insight is stored as a lesson and then
   influences future analyses.

PRAMANA addresses both problems by placing an execution-grounded verification
gateway between analysis and reporting/memory.

## 3. Proposed solution

```text
User uploads dataset
        |
        v
Ingestion and validation
        |
        v
Cleaning + schema inference + profiling
        |
        v
Analysis agent proposes CandidateInsight objects
        |
        v
Verification gateway
  - admissibility screening
  - falsification code generation
  - sandboxed execution
  - permutation/bootstrap statistics
  - Benjamini-Hochberg FDR correction
  - effect-size evidence gate
        |
        +--> PASS   --> proof object --> guarded ChromaDB memory --> report
        |
        +--> REJECT --> discarded / reported as rejected
```

The analysis module is a **proposer**, never a judge. It may propose plausible
claims, but it must not label them true, verified, or accepted.

## 4. Core technical idea

The gateway combines three safeguards:

### A. Actual execution

The model does not get to reason its way to a p-value. Generated falsification
code is executed in a controlled subprocess.

### B. Multiple-comparison correction

All testable claims from one run are treated as one statistical family. Raw
p-values are collected first, then Benjamini-Hochberg FDR correction produces
q-values.

BH correction is applied once per run, not separately to each insight.

### C. Evidence requires both significance and effect

A small p-value alone is insufficient. A claim must also have a meaningful
effect size according to configured thresholds. This avoids reporting
statistically significant but practically negligible relationships.

## 5. Technology stack

| Layer | Technology | Role |
|---|---|---|
| Data processing | Python, pandas, NumPy, SciPy | Load, clean, profile, and analyze datasets |
| Data contracts | Pydantic | Validate candidate insights and proof objects |
| Routine analysis model | Gemma/local model | Cheap schema and semantic assistance |
| Verification code generation | DeepSeek V4/API or deterministic templates | Produce falsification programs |
| Verification execution | Python subprocess/Celery worker | Execute untrusted generated code with limits |
| Workflow | LangGraph | Coordinate ingestion, analysis, verification, memory, and reporting |
| Task queue | Celery + Redis | Asynchronous execution and retry handling |
| Verified memory | ChromaDB | Store only verified lessons |
| Backend | FastAPI | API surface for runs, results, and memory |
| Observability | Langfuse + structured logging | Trace model calls and runs |
| Deployment | Docker | API and worker environments |

## 6. Team ownership and contributions

### P. Rohith — CB.AI.U4AID23123

**Owned area:** `src/pramana/analysis/`

Responsibilities:

- CSV/XLSX ingestion and safety limits
- Data cleaning and quality reporting
- Schema inference
- Descriptive profiling
- Correlation, group-difference, and trend candidate strategies
- Candidate prioritization
- Benchmark source curation and contamination screening
- Reproducible demo dataset construction

Current implementation includes:

- Public handlers: `ingest`, `prepare`, and `analyze`
- Pydantic-compatible `CandidateInsight` generation
- Unique insight IDs
- Exact cleaned `dataset_ref` propagation
- Candidate ranking and configurable caps
- A diabetes demo builder with a seeded false/noise relationship

Relevant files:

- [`src/pramana/analysis/public.py`](../src/pramana/analysis/public.py)
- [`src/pramana/analysis/ingestion.py`](../src/pramana/analysis/ingestion.py)
- [`src/pramana/analysis/cleaning.py`](../src/pramana/analysis/cleaning.py)
- [`src/pramana/analysis/profiling.py`](../src/pramana/analysis/profiling.py)
- [`src/pramana/analysis/hypotheses/`](../src/pramana/analysis/hypotheses/)
- [`src/pramana/analysis/benchmark/`](../src/pramana/analysis/benchmark/)

### B. Karthikeya — CB.AI.U4AID23109

**Owned area:** `src/pramana/orchestration/`, `src/pramana/common/`, Docker
tooling.

Responsibilities:

- LangGraph workflow/spine
- Shared graph state
- Node adapters
- Celery and Redis plumbing
- Run lifecycle and retries
- Docker API/worker environments
- Module integration

There is a separate branch named
`origin/feat/b-karthikeya/orchestration-spine` containing substantial
orchestration and Docker work. It should be described as integration work in
progress unless it has been merged into the presentation branch.

### P.P. Satya Karthikeya — CB.AI.U4AID23128

**Owned areas:** `src/pramana/contracts/`, `src/pramana/verification/`, and
later `src/pramana/evaluation/`.

Responsibilities:

- Shared `CandidateInsight` and `ProofObject` contracts
- Vetted permutation/bootstrap statistics
- Effect-size metrics
- Benjamini-Hochberg FDR correction
- Evidence scoring and PASS/REJECT gate
- Falsification code generation
- Sandboxed execution policy
- Gateway orchestration
- Memory guard
- Evaluation and ablation metrics

The deterministic verification core is documented as implemented through phases
1–5:

1. Contracts
2. Statistics library
3. BH-FDR
4. Evidence gate
5. Sandboxed executor

The full gateway orchestrator, live LLM generator path, and memory guard are
still identified as remaining integration work in
[`docs/IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md).

### M. Karthik Reddy — CB.AI.U4AID23131

**Owned areas:** `src/pramana/memory/`, `src/pramana/api/`,
`src/pramana/dashboard/`.

Responsibilities:

- ChromaDB schema and verified lessons
- Guarded memory write path
- Lesson abstraction and retrieval
- Dataset fingerprinting
- FastAPI backend services
- Dashboard and deployment

The memory layer consumes proof objects. It must not recompute or override
verification decisions.

## 7. Shared contracts

### CandidateInsight

The analysis module sends candidates to the verification gateway:

```json
{
  "insight_id": "unique-id",
  "claim": "bmi is associated with age",
  "claim_type": "correlation",
  "variables": ["age", "bmi"],
  "dataset_ref": "path/to/cleaned/frame.pkl",
  "analysis_evidence": {
    "stat": "spearman_rho",
    "raw_value": 0.45
  }
}
```

Important properties:

- `insight_id` is unique within a run.
- `dataset_ref` points to the exact cleaned dataframe used to create the
  candidate.
- `analysis_evidence` is exploratory evidence only.
- No candidate contains a PASS or REJECT decision.

### ProofObject

The gateway sends proof objects downstream:

```json
{
  "insight_id": "unique-id",
  "verdict": "PASS",
  "p_value": 0.004,
  "q_value": 0.012,
  "effect_size": 0.42,
  "evidence_score": 0.81,
  "test_type": "permutation",
  "falsification_code": "executed source",
  "n_hypotheses_in_batch": 12
}
```

The contract enforces:

- `PASS` is valid only for a supported claim.
- Untested claims do not receive fabricated statistical values.
- Evidence scores exist only for supported findings.
- Failed, malformed, or timed-out execution fails closed.

## 8. Rohith's analysis pipeline

```text
ingest(path)
  -> load CSV/XLSX
  -> enforce file and row limits
  -> replace common missing markers

prepare(payload)
  -> copy dataframe
  -> remove unusable columns/duplicates
  -> report data-quality findings
  -> infer numeric/categorical/datetime/ordinal/ID-like columns
  -> persist cleaned dataframe as a worker-readable pickle
  -> return dataset_ref + schema_profile

analyze(prepared_payload)
  -> correlation candidates
  -> categorical/numeric group-difference candidates
  -> datetime/numeric trend candidates
  -> deduplicate and rank
  -> cap candidates
  -> return CandidateInsight list
```

The analysis module deliberately uses hedged language such as:

- “is associated with”
- “tends to be higher in”

It does not use causal or universal claims such as “causes”, “always”, or
“guarantees”.

## 9. Demo dataset

The supplied local source is the UCI Diabetes 130-US Hospitals dataset:

```text
C:\Users\saich\Downloads\demodataset\diabetic_data.csv
```

The repository provides:

```python
from pramana.analysis.benchmark.demo_dataset import build_demo_from_diabetes

build_demo_from_diabetes(
    r"C:\Users\saich\Downloads\demodataset",
    r"data\demo\pramana_diabetes_demo.csv",
    rows=1000,
    seed=20260817,
)
```

The generated demo:

- contains 1,000 rows and 12 columns;
- retains hospital, demographic, utilization, and readmission variables;
- is reproducible using a fixed seed;
- adds `injected_false_signal`;
- independently shuffles a numeric source column to create a known noise
  relationship;
- remains under the ignored `data/` directory and is not committed.

For a live presentation, show:

1. A meaningful relationship proposed by the analysis module.
2. The injected false/noise relationship also being proposed as a candidate.
3. The verification gateway testing both.
4. The real signal receiving a proof-backed result.
5. The false signal being rejected rather than written to memory.

## 10. Benchmark and evaluation design

The planned evaluation uses 40 datasets and four conditions:

| Condition | Description |
|---|---|
| A | Single LLM call, no agent loop |
| B | Agent loop without verification |
| C | Agent loop with an evaluation-only LLM judgement mode |
| D | Full PRAMANA with execution-grounded verification |

The planned benchmark uses real open-data marginals, independently shuffles
columns to remove unknown associations, then injects relationships with known
type, effect size, and direction. This creates complete ground truth:

- injected relationships are positive examples;
- all other pairs are known nulls.

Metrics:

- precision of reported insights;
- recall of injected relationships;
- empirical false discovery rate;
- batch versus episode-mode self-evolution.

The current repository has the analysis-side manifest and contamination
screening utilities. The full 40-dataset evaluation harness is a later work
item and should not be presented as completed.

## 11. Security and reliability principles

### Fail closed

Crashes, timeouts, malformed payloads, invalid provenance, and insufficient
evidence cannot produce `PASS`.

### Restricted generated code

Generated code is treated as untrusted. The executor applies:

- static import checks;
- an allowed-import list;
- subprocess isolation;
- timeout limits;
- memory/resource limits;
- payload and provenance validation.

### No unverified memory

Only the guarded memory path can write lessons. A rejected or untested
insight cannot reach ChromaDB.

### Reproducibility

Seeds, configuration, dataset references, proof objects, and batch identifiers
are recorded so results can be audited and rerun.

## 12. Current status snapshot

| Area | Status |
|---|---|
| Project architecture and ownership | Defined |
| Shared contracts | Implemented |
| Rohith ingestion | Implemented |
| Rohith cleaning/profiling | Implemented |
| Schema inference | Implemented with deterministic heuristics |
| Candidate generation | Correlation, group difference, and trend implemented |
| Candidate prioritization | Implemented with configurable cap |
| Benchmark manifest/screening | Implemented |
| Reproducible diabetes demo builder | Implemented |
| Verification statistics | Implemented according to verification status document |
| BH-FDR | Implemented according to verification status document |
| Sandboxed executor | Implemented according to verification status document |
| Full verification gateway | Integration work remaining |
| Memory guard | Integration work remaining |
| Full API/dashboard deployment | Work in progress |
| 40-dataset evaluation run | Planned/later work |

## 13. Known limitations to state honestly

1. The full end-to-end product path is not yet complete on the current branch.
2. The verification gateway and memory guard still have integration work
   identified in the repository status documentation.
3. Effect-size thresholds are documented as provisional and require calibration
   against the final demo/benchmark data.
4. The 40-dataset evaluation harness and final results are not yet complete.
5. The current demo uses a local diabetes dataset source; raw data is kept
   outside Git.
6. The project should not claim that a p-value alone proves an insight.
7. The project should not claim causal discovery from observational data.

## 14. Suggested presentation structure

### Slide 1 — Title

**PRAMANA: Execution-Grounded Verification for Self-Evolving Data Analysis**

Team AB-07, Amrita School of AI.

### Slide 2 — Motivation

- LLMs can hallucinate statistical relationships.
- Unverified memory creates compounding errors.
- Existing agents often report plausible claims without executing tests.

### Slide 3 — Proposed architecture

Show the pipeline from upload to analysis, verification, memory, and report.

### Slide 4 — Core novelty

Explain:

- executable falsification;
- BH-FDR across the complete batch;
- effect-size gating;
- PASS-only memory writes.

### Slide 5 — Team contributions

Use the ownership table from Section 6.

### Slide 6 — Rohith's analysis module

Show the ingestion, preparation, schema, profiling, hypothesis-generation,
prioritization, and benchmark flow.

### Slide 7 — Shared contracts

Show the `CandidateInsight` input and `ProofObject` output.

### Slide 8 — Demo

Use the diabetes demo. Show one plausible relationship and the injected
false/noise relationship.

### Slide 9 — Evaluation

Explain the A/B/C/D conditions, the 40-dataset plan, and precision/recall/FDR.

### Slide 10 — Safety and limitations

Explain fail-closed behavior, sandboxing, reproducibility, and what remains.

### Slide 11 — Expected impact

PRAMANA is not just an LLM that generates insights. It is an analysis system
that attaches executable evidence to every insight and prevents unverified
claims from becoming persistent knowledge.

## 15. Short viva explanation

> PRAMANA separates proposing from proving. The analysis agent can suggest
> correlations, group differences, and trends, but those suggestions are not
> trusted. The verification gateway executes falsification tests, corrects for
> multiple hypotheses, checks practical effect size, and creates a proof object.
> Only a supported result can be stored in verified memory. This prevents both
> one-time hallucinated reports and long-term memory poisoning.

## 16. Repository references

- [Project context](../PROJECT.md)
- [Repository README](../README.md)
- [Ownership map](../OWNERSHIP.md)
- [Rohith scope](../scope/SCOPE_P_Rohith.md)
- [Verification status](IMPLEMENTATION_STATUS.md)
- [Open issues and decisions](OPEN_ISSUES.md)
- [Rohith analysis notes](ROHITH_ANALYSIS.md)
- [Evaluation specification](../src/pramana/evaluation/SPEC.md)
