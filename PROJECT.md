# PROJECT.md — PRAMANA

> Context file for AI coding agents. Read this FIRST before touching any code.
> Companion files: `AGENTS.md` (rules you must follow), `SCOPE.md` (current work scope).

## 1. What is PRAMANA

PRAMANA (Sanskrit: "valid proof") is a **self-evolving data analysis agent with execution-grounded verification**.

**One-line pitch:** An LLM agent that analyzes datasets and reports insights — but every insight must survive actual code execution and statistical falsification tests before it is (a) shown to the user or (b) written to long-term memory.

**The problem it solves:**
1. LLM agents hallucinate statistical claims — they "see" correlations that don't survive testing.
2. Self-improving agents suffer **memory poisoning**: unverified lessons get stored and corrupt all future analyses.

**The fix:** A verification gateway sits between raw analysis output and everything downstream. Nothing unverified passes. Memory stays clean by construction.

## 2. High-level workflow

```
User uploads dataset (+ optional question)
        │
        ▼
[1] Sub-agents (Gemma, local)          → schema inference, cleaning, column classification
        │
        ▼
[2] Analysis agent                     → proposes candidate insights (correlations, group
        │                                 differences, trends)
        ▼
[3] VERIFICATION GATEWAY (DeepSeek V4) → per insight:
        │                                 - generate falsification code
        │                                 - EXECUTE it (permutation test / bootstrap)
        │                                 - Benjamini-Hochberg FDR correction across all
        │                                   hypotheses in the run
        │                                 - evidence score → verdict PASS / REJECT
        ▼
[4] Memory write (ChromaDB)            → ONLY PASSed insights are abstracted into lessons
        │                                 and stored. REJECTed insights are discarded.
        ▼
[5] Report to user                     → each insight ships with its proof object
                                          (verdict, p-value, q-value, effect size,
                                          evidence score)
```

Across sessions ("episode mode"): on a new related dataset, the agent retrieves verified lessons from ChromaDB instead of starting cold. Self-evolution is measured by comparing batch vs. episode performance.

## 3. Architecture / tech stack

| Layer | Tech | Notes |
|---|---|---|
| Orchestration | LangGraph | agent graph / state machine |
| Backend API | FastAPI | |
| Routine sub-agent LLM | Gemma (local) | schema inference, cleaning, classification — cheap tasks |
| Verification LLM | DeepSeek V4 (API) | trust-critical step ONLY — do not swap to local model |
| Verified memory | ChromaDB | vector store; write access gated by verification verdict |
| Observability | Langfuse | tracing LLM calls |
| Task queue | Celery + Redis | async execution of falsification code |
| Deployment | Docker | |

**Model split rationale (do not change without team decision):** running the verification gate on a weak local model would undermine the core trust thesis. Gemma handles cheap routine work to control cost; DeepSeek V4 is reserved for verification.

## 4. Team & module ownership

Capstone project, Team AB-07, Amrita School of AI. Supervisor: Rayappa David Amar Raj.

| Member | Roll | Owns | Scope file |
|---|---|---|---|
| B. Karthikeya | CB.AI.U4AID23109 | System architecture & workflow: LangGraph orchestration, Docker execution environment, module integration | `SCOPE_B_Karthikeya.md` |
| P. Rohith | CB.AI.U4AID23123 | Data analysis module: ingestion, cleaning/profiling, hypothesis generation, evaluation dataset curation | `SCOPE_P_Rohith.md` |
| P.P. Satya Karthikeya | CB.AI.U4AID23128 | Verification & evaluation: verification gateway (falsification, FDR, evidence scoring), benchmarking, results analysis | `SCOPE.md` |
| M. Karthik Reddy | CB.AI.U4AID23131 | Memory & system deployment: verified memory framework (ChromaDB), backend services, cloud deployment, dashboard | `SCOPE_M_Karthik_Reddy.md` |

## 5. Key interfaces (contracts between modules)

**Analysis agent → Verification gateway:** list of candidate insights. Each candidate:
```json
{
  "insight_id": "str (unique per run)",
  "claim": "natural language statement of the insight",
  "claim_type": "correlation | group_difference | trend | distribution",
  "variables": ["col_a", "col_b"],
  "dataset_ref": "path or handle to the cleaned dataframe",
  "analysis_evidence": {"stat": "...", "raw_value": 0.0}
}
```

**Verification gateway → Memory / Report:** proof object per insight:
```json
{
  "insight_id": "str",
  "verdict": "PASS | REJECT",
  "p_value": 0.0,
  "q_value": 0.0,
  "effect_size": 0.0,
  "evidence_score": 0.0,
  "test_type": "permutation | bootstrap",
  "falsification_code": "the executed code (for audit trail)",
  "n_hypotheses_in_batch": 0
}
```

**Hard rule:** ChromaDB writes MUST check `verdict == "PASS"`. There is no other path into memory.

## 6. Evaluation design

Four-condition ablation over a **40-dataset benchmark**:

- **A** — single LLM call (no agent loop)
- **B** — agent loop, no verification gate
- **C** — agent loop + LLM critic (LLM judges insights, no execution)
- **D** — full PRAMANA (agent loop + execution-grounded gate)

Claim being tested: D achieves higher precision on reported insights than A/B/C. Results are framed as **directional trends** — n=40 gives thin statistical power, and this limitation is disclosed openly in the report, not hidden.

**Benchmark hygiene:** well-known datasets (Iris, Titanic, etc.) are EXCLUDED to avoid evaluating memorized knowledge instead of the pipeline.

## 7. Demo design

Live demo dataset: NHANES or NFHS-5 subset (~500–2,000 rows, 8–15 columns) with:
- one or more **real, published relationships** (gate should PASS them)
- one **injected false correlation** (gate should REJECT it)

This makes the gateway's value visible in one run: fake signal dies, real signal survives, both with proof objects attached.

## 8. Hard constraints (capstone rules)

- Team of four — frozen, no changes
- Deliverable must be product-oriented (working pipeline, not just a paper)
- AI-generated % in the written report: **under 20%**
- Plagiarism: **under 15%**
- MIMIC-IV is OFF LIMITS (PhysioNet zero-retention policy conflicts with our pipeline). Use NHANES / NFHS-5.
