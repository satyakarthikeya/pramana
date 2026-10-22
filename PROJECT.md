# PROJECT.md — PRAMANA

> Read this FIRST. Companions: `AGENTS.md` (rules), `SCOPE.md` (what we are doing now),
> `STATUS.md` (where we are today). Section numbers §2 and §5 are cited by code and
> `AGENTS.md`; do not renumber them.
> There are no per-person modules or scope files any more. One team, one product (V1).

## 1. What PRAMANA is

PRAMANA (Sanskrit: "valid proof") analyses a table of data and reports only the claims that
survive real statistical testing.

A person uploads a CSV or XLSX. PRAMANA proposes claims about it, **runs a permutation test
on each claim**, corrects for testing many claims at once (Benjamini-Hochberg), and shows
only the findings that survive, each with its proof. Everything else is shown separately as
*not a finding*, with the reason. Verified findings are remembered; past lessons are offered
as hints on later datasets, never as evidence.

**Core principle:** models *propose* and *write code*; code *decides*. Every statistic,
q-value and verdict comes from our own tested code. No model output is evidence.

**Invariant:** `memory_write ⟹ verdict == PASS`. Nothing unverified reaches the user as a
finding or reaches memory.

## 2. Workflow

```
Upload dataset (+ optional question)
   │
[0] Memory lookup   → verified lessons from similar past datasets, shown as HINTS only
[1] Preparation     → ingest, clean (rules), profile, infer schema; code applies and logs every step
[2] Claim proposal  → STRUCTURED claims (claim_type, variables, direction, reference group).
   │                  Code renders the sentence from a hedged template. Batch is capped.
   │                  Proposed by DeepSeek (API); a deterministic rule scan is an explicit
   │                  offline/reference mode, never a silent fallback.
[3] VERIFICATION GATEWAY  (one call, one BH family)
   │   a. admissibility screen   refuses universal / causal wording and unknown columns
   │                             → NOT_TESTABLE (excluded from the BH family)
   │   b. falsification code     DeepSeek-written falsify(frame) (default) or the template
   │                             generator (explicit offline mode); both may only CALL
   │                             pramana.verification.stats
   │   c. code check             parses, right seed/permutations, allowed imports, own columns only
   │   d. sandboxed execution    subprocess, timeout, import whitelist, HMAC stamp on the numbers
   │                             crash / timeout / bad stamp → p = 1.0 → INCONCLUSIVE
   │   e. Benjamini-Hochberg     once, over every TESTED claim → q-values
   │   f. gate                   q < alpha → |effect| >= metric floor → direction matches
   │                             SUPPORTED → PASS; everything else → REJECT
   │   g. proof object           one per candidate, in input order (§5)
[4] Memory write    → the memory guard admits PASS proofs only and raises on anything else
[5] Report          → verified findings with proofs; rejected claims listed with reasons
```

Rules across the whole flow:

- **One run = one gateway call = one BH family.** Each candidate is tested exactly once;
  a REJECTed claim is never revised and resubmitted in the same run. Retries cover crashed code only.
- **Screened claims are not in the family** (they consumed no test).
- **Fail closed everywhere.** No failure, timeout or missing dependency can produce a PASS.
- **No silent model substitution.** A run configured for a model gets that model's output or fails closed.

## 3. Architecture

| Layer | Tech | Notes |
|---|---|---|
| Product | `python -m pramana` | local web app on port 8080; in-process verification by default; one run at a time |
| Backend API | FastAPI | upload, runs, results, memory list/search, health |
| Dashboard | static HTML/JS | progress, preview, finding cards, readable/raw proofs, export, memory |
| Orchestration | LangGraph | ingest → prepare → analyse → gateway → memory → report |
| Verification | `src/pramana/verification/` | stats library, FDR, gate, sandbox executor, generators, memory guard |
| Memory | ChromaDB + all-MiniLM-L6-v2 | local, gitignored store |
| Models | DeepSeek API only (one `DEEPSEEK_API_KEY`) | structured claim proposals and falsification code, separate prompts; Gemma/Ollama removed (PR #26). Schema inference, cleaning and lesson text are deterministic code |
| Tracing | Langfuse | every LLM call is traced under the run ID; the live profile needs Langfuse credentials as well as the DeepSeek key |
| Optional / not on the V1 path | Celery/Redis, Docker/cloud deploy | exist in the repo; in-process is the V1 default |

Trust does not come from the model being smart. The generated program is a thin harness
around our vetted library, inside a sandbox that blocks statistics libraries; the p-value,
BH correction, gate and verdict are deterministic code. The stored `falsification_code`
and seed reproduce every number exactly; regenerating the code is not expected to.

## 4. Team

Capstone project, Team AB-07, Amrita School of AI. Supervisor: Rayappa David Amar Raj.
Team of four, frozen: B. Karthikeya, P. Rohith, P.P. Satya Karthikeya, M. Karthik Reddy.
Anyone can take any item. Safety-critical review (PASS invariant, p-values, FDR, sandbox)
still follows `AGENTS.md` §8.

## 5. Contracts

The Pydantic models in `src/pramana/contracts/` are **authoritative**; the JSON below is a
summary. If they disagree, the code wins and this section is the bug.

**Claim proposal → gateway** (`CandidateInsight`):

```json
{
  "insight_id": "str (unique per run)",
  "claim": "sentence rendered by code from a hedged template",
  "claim_type": "correlation | group_difference | trend | distribution",
  "variables": ["col_x", "col_y"],
  "dataset_ref": "reference to the exact cleaned dataframe",
  "analysis_evidence": {"stat": "...", "raw_value": 0.0, "n_observations": 0},
  "asserted_direction": "positive | negative | null",
  "reference_group": "str | null"
}
```

`analysis_evidence` is never trusted as proof and never carries a p-value, q-value or verdict.
`distribution` has no test yet, so the gateway screens it out as NOT_TESTABLE.

**Gateway → memory / report** (`ProofObject`):

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
  "falsification_code": "the executed code (audit trail)",
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

`verdict` is PASS iff `gate_outcome` is `supported`. Statistical fields are null exactly when
the claim was never tested (`not_testable`); `evidence_score` is present exactly for
`supported` claims and is for ranking only.

**Hard rule:** memory writes MUST check `verdict == "PASS"`. There is no other path in.

## 6. Evaluation (after V1)

Four-condition ablation on a 40-dataset benchmark: A single LLM call; B agent loop, no gate;
C agent loop + LLM critic (must be built to win); D full PRAMANA. Results are framed as
directional trends (n = 40, thin power, disclosed). Famous datasets are excluded. Only A and
D are built. Not part of V1.

## 7. Demo

NHANES-style data (~500–2,000 rows, 8–15 columns) with real relationships (should PASS) and
an injected false correlation (should REJECT). The injected decoy must be one the proposer
actually proposes, or it demonstrates nothing.

## 8. Hard constraints

- Product-oriented deliverable: a working pipeline, not just a paper.
- Written report under 20% AI-generated and under 15% plagiarism (`AGENTS.md` §7).
- MIMIC-IV is forbidden. Use NHANES / NFHS-5 / other open data. No raw data in git.
