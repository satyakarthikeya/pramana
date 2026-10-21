# PROJECT.md — PRAMANA

> Context file for AI coding agents. Read this FIRST before touching any code.
> Companion files: `AGENTS.md` (rules you must follow), `SCOPE.md` (current work scope).
> This file describes the **target design**. What is built today is marked in the
> "Where models are used" table in §2 and tracked in `docs/DECISIONS_LLM_ROLES.md`.
> Do not assume a component exists because it appears in a diagram here.

> **Provider update, 21 October 2026:** the user explicitly requested DeepSeek-only
> generative inference. Analysis now proposes structured claims through DeepSeek;
> the gateway separately asks DeepSeek to write falsification code. Gemma/Ollama
> inference is removed. Schema, cleaning and lesson formatting are rules only;
> optional semantic-refiner hooks are not live model implementations. MiniLM is
> retained for local embeddings, not generation. This supersedes historical model
> names/split rationale below. All hosted calls require run-linked Langfuse tracing.
> No statistical threshold, sandbox or PASS-only memory contract is changed.
> Live smoke/browser/group/trend/replay checks are recorded in
> `docs/team/DEEPSEEK_LIVE_TEST_LOG.md`. Affected-owner reviews, broad evaluation
> and release gates remain tracked in `docs/team/DEEPSEEK_ONLY_TODO.md`.

## 1. What is PRAMANA

PRAMANA (Sanskrit: "valid proof") is a **self-evolving data analysis agent with execution-grounded verification**.

**One-line pitch:** An LLM agent that analyzes datasets and reports insights — but every insight must survive actual code execution and statistical falsification tests before it is (a) shown to the user or (b) written to long-term memory.

**The problem it solves:**
1. LLM agents hallucinate statistical claims — they "see" correlations that don't survive testing.
2. Self-improving agents suffer **memory poisoning**: unverified lessons get stored and corrupt all future analyses.

**The fix:** A verification gateway sits between raw analysis output and everything downstream. Nothing unverified passes. Memory stays clean by construction.

**The core principle:** models *propose* and *write code*; code *decides*. An LLM may suggest a claim or write the program that tests it, but every statistic, every q-value and every verdict is produced by our own tested code. No model output is ever treated as evidence.

## 2. High-level workflow

```
User uploads dataset (+ optional question)
        │
        ▼
[0] Memory lookup (episode mode)       → retrieve verified lessons from similar past
        │                                 datasets. Given to [2] as HINTS only: a lesson
        │                                 is never reported as an insight about the new
        │                                 dataset unless it passes [3] on that dataset.
        ▼
[1] Preparation                        → ingest, clean (rules), infer the schema.
        │                                 No semantic model is currently wired here:
        │                                 an optional future refiner may suggest a
        │                                 cleaning step. Code applies and logs any step;
        │                                 a model must never edit data itself.
        ▼
[2] Analysis agent (LLM)               → reads the schema profile, column summaries, the
        │                                 user's question and [0]'s hints, and proposes
        │                                 STRUCTURED claims: claim_type, variables,
        │                                 direction, reference group.
        │                                 Code (not the LLM) renders each claim's sentence
        │                                 from a hedged template. The batch is capped.
        │                                 The agent is allowed to be wrong — [3] exists to
        │                                 catch it.
        ▼
[3] VERIFICATION GATEWAY               → the whole batch in one call, one BH family:
        │   a. admissibility screen      code. Refuses universal ("always", "every") and
        │                                 causal ("causes") wording and unknown columns
        │                                 → NOT_TESTABLE, excluded from the BH family.
        │   b. write falsification code  DeepSeek V4 writes `falsify(frame)` for each
        │                                 claim. The code may only CALL our vetted library
        │                                 `pramana.verification.stats`; it computes nothing.
        │   c. check the code            code. Parses, defines falsify(frame), uses the
        │                                 run's seed and permutation count, imports only
        │                                 numpy / pandas / pramana.verification.stats,
        │                                 reads only the claim's own columns. Any failure
        │                                 → NOT_TESTABLE. No silent fallback.
        │   d. execute in the sandbox    code. Subprocess, timeout, import whitelist.
        │                                 Permutation test → raw p + effect size. An HMAC
        │                                 stamp proves the numbers came from our library.
        │                                 Crash / timeout / bad stamp → p = 1.0, stays in
        │                                 the family → INCONCLUSIVE.
        │   e. Benjamini-Hochberg        code. Once, over every TESTED claim → q-values.
        │   f. gate                      code. q < alpha → |effect| >= that metric's floor
        │                                 → observed direction matches the claim.
        │                                 SUPPORTED → PASS. INCONCLUSIVE / NEGLIGIBLE /
        │                                 REFUTED / NOT_TESTABLE → REJECT. The evidence
        │                                 score is computed for PASS only, for ranking;
        │                                 it never decides a verdict.
        │   g. proof object              one per candidate, in input order (§5).
        ▼
[4] Memory write                       → the memory guard admits PASS proofs only and
        │                                 raises on anything else. PASSed insights are
        │                                 abstracted into lessons (rules) and
        │                                 stored in ChromaDB. REJECTed ones are discarded.
        ▼
[5] Report to user                     → PASS insights, each with its proof object.
                                          Rejected claims are listed separately with the
                                          reason (gate outcome, p, q).
```

**Rules that hold across the whole flow:**

- **One run = one gateway call = one BH family.** Every candidate is tested exactly once. A REJECTed claim is never revised and resubmitted to the same gate within a run — that is testing after peeking. Graph-level retries cover crashed code only.
- **Screened claims are not in the family.** NOT_TESTABLE claims consumed no test, so they do not count toward `n_hypotheses_in_batch`.
- **Fail closed everywhere.** No failure, timeout or missing dependency can produce a PASS.

Across sessions ("episode mode"): on a new related dataset, the agent retrieves verified lessons from ChromaDB instead of starting cold ([0] above). Self-evolution is measured by comparing batch vs. episode performance.

**Where models are used** (implementation status, 21 October 2026; live evidence and limitations in the test log):

| Step | Model | What it may do | What it may never do | Status |
|---|---|---|---|---|
| [0] + [4] memory search | all-MiniLM-L6-v2 embeddings (local) | Find similar verified lessons | Decide what is stored | Persistent store, automatic historical hints and source links built |
| [1] schema inference | none (rules) | Classify supported columns | Guess unknown roles | Heuristics built; optional `SemanticRefiner` hook has no model implementation |
| [1] cleaning | none (rules) | Apply and log configured cleaning | Silently edit data | Rule-based implementation built |
| [2] analysis agent | DeepSeek API | Propose structured claims | Author claim prose, proof or verdict | Shared traced client exercised live; invalid/omitted proposals remain possible; deterministic baseline is explicit only |
| [3b] falsification code | DeepSeek API | Write `falsify(frame)` calling our library | Supply a statistic or verdict as evidence | LLM default; shared run-linked tracing, bounded transport and no fallback implemented |
| [3c] column check | none (code) | Refuse unstated columns and row selection | Relax sandbox restrictions | Built, along with template-agreement diagnostics |
| [4] lesson abstraction | none (rules) | Render a lesson from a PASS proof | Store a non-PASS claim | Rule-based abstraction and guarded writes built |
| everything else in [3], the memory guard | none (code) | — | — | Built |

**The template generator** (`verification/falsification/templates.py`) writes the same test for a claim type without any model. It stays as the reference the DeepSeek path is measured against and as an explicit offline mode, chosen in config. It is never a silent fallback: a run configured for DeepSeek either gets DeepSeek's code or a NOT_TESTABLE.

## 3. Architecture / tech stack

| Layer | Tech | Notes |
|---|---|---|
| Orchestration | LangGraph | agent graph / state machine |
| Backend API | FastAPI | |
| Routine operations | deterministic code | schema heuristics, cleaning, lesson formatting; no hidden generative calls |
| Analysis LLM | DeepSeek API | proposes structured claims only; separate prompt from verification |
| Verification LLM | DeepSeek V4 (API) | writes falsification code ONLY; that code may import just `numpy`, `pandas` and `pramana.verification.stats` — do not swap to a local model |
| Verified memory | ChromaDB + all-MiniLM-L6-v2 embeddings | vector store; write access gated by verification verdict |
| Observability | Langfuse | tracing every LLM call |
| Task queue | Celery + Redis | async execution of falsification code |
| Deployment | Docker | |

**Provider decision (user request, 21 October 2026):** DeepSeek handles both generative roles with separate prompts and boundaries. The analysis agent proposes hypotheses; the gateway's model writes the falsification harness. Routine operations stay deterministic. Accuracy comes from execution, validation and the guard, not from a model promising a correct answer. This cross-module migration requires affected-owner review before merge.

**Why DeepSeek writes the tests.** A template is one fixed test per claim type. It cannot adapt to a particular claim or dataset — a subgroup claim, a unit written into a column, a code like `0` meaning "not measured" — so such claims either fail as NOT_TESTABLE or get tested on the wrong values. DeepSeek writes the test each claim needs.

**Why that does not weaken trust.** DeepSeek's code is a thin harness around `pramana.verification.stats`: the permutation test and effect sizes are computed by our own tested code, the HMAC stamp proves every number came from it, and the p-value, BH correction, gate and verdict are deterministic code no model touches. The four code checks in [3c] run before execution; the column check closes the remaining gap, where stamped numbers could come from the wrong columns or an unstated subgroup. Using a weak local model here would still undermine the trust thesis, which is why verification does not use Gemma.

**Reproducibility with an LLM in the loop.** Each proof object stores the exact code that ran (`falsification_code`) and the seed, so re-running that code on the same data reproduces every number exactly. Asking DeepSeek again may produce different code; that is expected and is why the stored code, not the prompt, is the record.

## 4. Team & module ownership

Capstone project, Team AB-07, Amrita School of AI. Supervisor: Rayappa David Amar Raj.

| Member | Roll | Owns | Scope file |
|---|---|---|---|
| B. Karthikeya | CB.AI.U4AID23109 | System architecture & workflow: LangGraph orchestration, Docker execution environment, module integration | `SCOPE_B_Karthikeya.md` |
| P. Rohith | CB.AI.U4AID23123 | Data analysis module: ingestion, cleaning/profiling, hypothesis generation, evaluation dataset curation | `SCOPE_P_Rohith.md` |
| P.P. Satya Karthikeya | CB.AI.U4AID23128 | Verification & evaluation: verification gateway (falsification, FDR, evidence scoring), benchmarking, results analysis | `SCOPE.md` |
| M. Karthik Reddy | CB.AI.U4AID23131 | Memory & system deployment: verified memory framework (ChromaDB), backend services, cloud deployment, dashboard | `SCOPE_M_Karthik_Reddy.md` |

## 5. Key interfaces (contracts between modules)

The Pydantic models in `src/pramana/contracts/` are **authoritative**; the JSON below is a
summary. If the two ever disagree, the code wins and this section is the bug.

**Analysis agent → Verification gateway:** list of candidate insights (`CandidateInsight`). Each candidate:

```json
{
  "insight_id": "str (unique per run)",
  "claim": "natural-language statement, rendered by code from a hedged template",
  "claim_type": "correlation | group_difference | trend | distribution",
  "variables": ["col_x", "col_y"],
  "dataset_ref": "reference to the exact cleaned dataframe",
  "analysis_evidence": {"stat": "...", "raw_value": 0.0, "n_observations": 0},
  "asserted_direction": "positive | negative | null",
  "reference_group": "str | null (group_difference: the level the claim is about)"
}
```

`analysis_evidence` is what the analysis agent saw. It is never trusted as proof and never
carries a p-value, q-value or verdict. `distribution` is a valid value with no test yet, so
the gateway screens it out as NOT_TESTABLE.

**Verification gateway → Memory / Report:** one proof object per insight (`ProofObject`):

```json
{
  "insight_id": "str",
  "verdict": "PASS | REJECT",
  "gate_outcome": "supported | refuted | negligible | inconclusive | not_testable",
  "bh_family_id": "str",
  "seed": 0,
  "p_value": 0.0,
  "q_value": 0.0,
  "effect_size": 0.0,
  "effect_metric": "spearman_rho | kendall_tau_b | cliffs_delta | epsilon_squared | cramers_v",
  "test_type": "permutation | bootstrap",
  "falsification_code": "the executed code (for audit trail)",
  "n_hypotheses_in_batch": 0,
  "reported_effect": 0.0,
  "reported_effect_metric": "str",
  "asserted_direction": "positive | negative | null",
  "observed_direction": "positive | negative | null",
  "outlier_warning": false,
  "evidence_score": 0.0,
  "score_components": {"s_q": 0.0, "s_e": 0.0, "s_r": 0.0},
  "failure_reason": "str | null"
}
```

`verdict` is PASS if and only if `gate_outcome` is `supported`. The statistical fields are
null exactly when the claim was never tested (`not_testable`); `evidence_score` is present
exactly for `supported` claims.

**Hard rule:** ChromaDB writes MUST check `verdict == "PASS"`. There is no other path into memory.

## 6. Evaluation design

Four-condition ablation over a **40-dataset benchmark**:

- **A** — single LLM call (no agent loop)
- **B** — agent loop, no verification gate
- **C** — agent loop + LLM critic (LLM judges insights, no execution)
- **D** — full PRAMANA (agent loop + execution-grounded gate)

"Agent loop" means the LLM analysis agent of §2 [2]; all four conditions use the same model and the same inputs. The critic in C exists only as an evaluation mode, never in the product, and it must be built to win (`docs/OPEN_ISSUES.md` issue 3). D is additionally run with the template generator, to measure what DeepSeek-written tests change.

Claim being tested: D achieves higher precision on reported insights than A/B/C. Results are framed as **directional trends** — n=40 gives thin statistical power, and this limitation is disclosed openly in the report, not hidden.

**Benchmark hygiene:** well-known datasets (Iris, Titanic, etc.) are EXCLUDED to avoid evaluating memorized knowledge instead of the pipeline.

## 7. Demo design

Live demo dataset: NHANES or NFHS-5 subset (~500–2,000 rows, 8–15 columns) with:

- one or more **real, published relationships** (gate should PASS them)
- one **injected false correlation** (gate should REJECT it)

This makes the gateway's value visible in one run: fake signal dies, real signal survives, both with proof objects attached.

The injected false correlation must be one the analysis agent actually proposes. A signal the agent never proposes never reaches the gate and demonstrates nothing, so the injection is validated against the real agent before the demo.

## 8. Hard constraints (capstone rules)

- Team of four — frozen, no changes
- Deliverable must be product-oriented (working pipeline, not just a paper)
- AI-generated % in the written report: **under 20%**
- Plagiarism: **under 15%**
- MIMIC-IV is OFF LIMITS (PhysioNet zero-retention policy conflicts with our pipeline). Use NHANES / NFHS-5.
