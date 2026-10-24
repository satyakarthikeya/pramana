# PROJECT.md: PRAMANA

> What the project is now and how it fits together. Companions: `STATUS.md` (where we
> are), `docs/ROADMAP.md` (what comes next), `SCOPE.md` (what is in and out), `AGENTS.md`
> (rules). Code, configs and `AGENTS.md` cite §2, §3, §5, §6 and §7 by number; keep the
> numbers and titles. New material goes in a new section at the end.
> Last rewritten 25 October 2026 against `chore/satya/cleanup-for-review`.

## 1. What PRAMANA is

PRAMANA (Sanskrit: "valid proof") reads a table and writes an analyst-style report.
Every number in it is computed by code, and each part is labelled with how far it can
be trusted:

| Level | What it is | Where it comes from |
|---|---|---|
| **Exact** | Arithmetic on the table: period change, price/volume/mix, segment growth, customers and RFM, seasonality, margins, concentration, outliers, data quality. Ordered as a story, with up to five "what to watch" questions | `src/pramana/analysis/computed/` |
| **Measured** | A closed menu of models scored on held-out rows against a baseline: drivers (ridge, logistic, forest, boosting, SVM, KNN), segments with profiles, anomalies, components (PCA), forecast, threshold, adjusted association. Not a significance test | `src/pramana/analysis/measured/` |
| **Tested** | Claims that went through the verification gateway: permutation test on held-back rows, Benjamini-Hochberg across the run, effect bands, attacks, spec hash, interval and power note. Only PASS reaches memory | `src/pramana/verification/` |

The web app has three tabs per dataset: **Report** (Exact and Measured), **Checked
claims** (gateway runs and their proofs) and **Ask** (chat over the table).

**Core principle:** models propose from closed menus; code computes and decides. No
model output is a statistic, a q-value or a verdict. DeepSeek is the only generative
provider. In the gateway the default test generator is `template` (a vetted test per
claim type and permutation scheme); DeepSeek-written tests (`llm`) are opt-in.

**Invariant:** `memory_write ⟹ verdict == PASS`. A FRAGILE claim is a REJECT and is
never stored.

## 2. Workflow

Where each model sits (AGENTS.md §2) and what is built. Every step below is built
unless marked otherwise.

```
UPLOAD (CSV / XLSX, up to configs/analysis.yaml max_rows)
  ingest, clean (rules, logged), profile, schema inference (rules)
  Data reader brief (code)
  sector match       rules, or DeepSeek from column NAMES only (sector_engine: api)
  EXACT tier         code, on the full table; story order + "what to watch" questions
  summary            code-written; DeepSeek may reword it (summary_engine: api), checked
                     number by number; falls back to the code text with the reason shown
  MEASURED tier      background task after upload; closed model menu, held-out scoring

ANALYSE (one run, optional question)
 [0] memory lookup   past PASS lessons shown as HINTS to re-test, never as evidence
 [1] split           seeded exploration / confirmation split (random rows, by entity, or
                     by time with later periods held back); verification/schemes.py
 [2] proposal        on EXPLORATION rows only. Engine (PRAMANA_ANALYSIS_ENGINE):
                       api (default)  DeepSeek proposes structured claims from summaries
                       planner        DeepSeek reads Exact/Measured results on exploration
                                      rows and returns a structured plan; code validates it
                       agent          DeepSeek with fixed tools and a bounded workspace
                       deterministic  rule scan, explicit offline mode
                     Code renders every claim sentence. Claim filters drop bookkeeping
                     pairs and time labels (planner path only). Trend claims are dropped,
                     with a recorded reason, when the table has more than 3,000 rows.
 [3] VERIFICATION GATEWAY (one call, one BH family), on CONFIRMATION rows only
     a. admissibility   universal / causal wording, unknown columns, untestable types
                        -> NOT_TESTABLE (not in the BH family)
     b. scheme          free / block_differenced / stratified / cluster / paired, chosen
                        from the table's structure
     c. test code       template (default) or DeepSeek-written falsify(frame) (llm, opt-in);
                        either may only CALL pramana.verification.stats
     d. code check      parses, right seed and permutations, allowed imports, own columns
     e. sandbox         subprocess, timeout, memory cap, import whitelist, HMAC stamp;
                        crash / timeout / bad stamp -> p = 1.0 -> INCONCLUSIVE
     f. spec hash       a result under a different seed or resample count is refused
     g. Benjamini-Hochberg  once over every TESTED claim -> q-values
     h. gate            q < alpha, |effect| >= metric floor, direction matches -> SUPPORTED
     i. attacks A1-A7   on SUPPORTED claims only; a BROKEN attack -> FRAGILE (a REJECT).
                        Optional refuter (off by default) may only ADD controls
     j. interval        percentile bootstrap beside the effect; shown, does not gate;
                        none for block-differenced trends
     k. power note      on non-significant claims: the smallest effect it could detect
     l. look ledger     how many earlier runs used the same held-back rows (disclosure)
     m. proof object    one per candidate, in input order (§5)
 [4] memory write    the memory guard admits PASS proofs only and raises otherwise
 [5] advisory        after the graph, on copies: Explainer sentence (code by default,
                     DeepSeek optional) and Skeptic confound caveats (code only)
 [6] report          held-up claims with proofs; rejected claims with reasons

ASK (chat)          DeepSeek uses fixed descriptive tools and either answers (numbers
                    checked against tool results) or proposes ONE structured claim, which
                    the gateway tests as a family of one (q = p, labelled "single test,
                    not corrected"). Never written to memory.
```

Rules across the whole flow:

- **One run = one gateway call = one BH family.** Each candidate is tested once; a
  REJECTed claim is never revised and resubmitted in the same run. Retries cover crashed
  code only.
- **Screened claims are not in the family** (they consumed no test).
- **Fail closed everywhere.** No failure, timeout or missing dependency can produce a
  PASS. DeepSeek calls need Langfuse credentials and fail closed without them.
- **No silent model substitution.** A run configured for a model gets that model's
  output or fails closed. The template generator is chosen in config, never as a fallback.
- Exact, Measured, advisory and chat output never enter the gateway's decision or memory.

## 3. Architecture

| Layer | Tech | Notes |
|---|---|---|
| Start | `python -m pramana [--port 8080] [--generator template\|llm]` | serves the API and the built UI on 127.0.0.1; one run at a time |
| Backend API | FastAPI (`src/pramana/api/`) | accounts (scrypt hashes, server-side sessions), datasets, runs, results, chat, memory, system |
| Web UI | React 18 + Vite + TypeScript (`web/`) | build to `web/dist` with `npm ci && npm run build` |
| Orchestration | LangGraph (`src/pramana/orchestration/`) | ingest, prepare, analyse, gateway, memory, report; advisory runs after the graph (`api/service.py`) |
| Verification | `src/pramana/verification/` | stats library, schemes, gateway, attacks, interval, power, spec, looks, FDR, sandbox, memory guard |
| Memory | ChromaDB + all-MiniLM-L6-v2 | local, under the gitignored data dir; embeddings are not a generative model |
| Models | DeepSeek API only (`DEEPSEEK_API_KEY`) | separate roles and prompts: proposer, planner, agent, test writer (opt-in), chat, explainer (opt-in), refuter (off), sector reader, report writer |
| Tracing | Langfuse | every model call is traced under the run or dataset id |
| Optional | Celery/Redis, Docker Compose (`docker/`) | Docker runs API + ChromaDB + UI; not exercised for gateway v3 (see STATUS.md) |

Trust does not come from the model. A generated test is a thin harness around the
vetted library, run in a sandbox whose import whitelist (`numpy`, `pandas`,
`pramana.verification.stats`) contains no statistics library, so generated code cannot
compute its own p-value. The p-value, BH correction, gate and verdict are deterministic
code. The stored `falsification_code` and seed reproduce every number; regenerating the
code is not expected to.

## 4. Team

Capstone project, Team AB-07, Amrita School of AI. Supervisor: Rayappa David Amar Raj.
Team of four: B. Karthikeya, P. Rohith, P.P. Satya Karthikeya, M. Karthik Reddy.
P.P. Satya Karthikeya is the verification owner. Anyone can take any item; changes to
the PASS invariant, p-values, FDR, the split or sandbox safety need the verification
owner's approval (`AGENTS.md` §8.10).

## 5. Contracts

The Pydantic models in `src/pramana/contracts/` are **authoritative**; this is a summary.
If they disagree, the code wins and this section is the bug.

**Claim proposal -> gateway** (`CandidateInsight`, frozen, unknown fields refused):

```json
{
  "insight_id": "str (unique per run)",
  "claim": "sentence rendered by code from a hedged template",
  "claim_type": "correlation | group_difference | trend | period_change | seasonality | distribution",
  "variables": ["col_x", "col_y"],
  "dataset_ref": "reference to the exact cleaned dataframe",
  "analysis_evidence": {"stat": "...", "raw_value": 0.0, "n_observations": 0},
  "asserted_direction": "positive | negative | null",
  "reference_group": "str | null"
}
```

`analysis_evidence` is never proof and never carries a p-value, q-value or verdict.
Testable types are correlation, group_difference, trend, period_change and seasonality
(`verification/admissibility.py`, `TESTABLE_CLAIM_TYPES`); `distribution` has no test and
is screened out as NOT_TESTABLE. Every testable claim names exactly two columns.

**Gateway -> memory / report** (`ProofObject`):

```json
{
  "insight_id": "str",
  "verdict": "PASS | REJECT",
  "gate_outcome": "supported | refuted | negligible | inconclusive | not_testable | fragile",
  "bh_family_id": "str",
  "seed": 0,
  "p_value": 0.0,
  "q_value": 0.0,
  "effect_size": 0.0,
  "effect_metric": "spearman_rho | kendall_tau_b | cliffs_delta | epsilon_squared | cramers_v | relative_change",
  "test_type": "permutation | bootstrap",
  "falsification_code": "the executed code (audit trail)",
  "n_hypotheses_in_batch": 0,
  "reported_effect": 0.0,
  "reported_effect_metric": "str",
  "asserted_direction": "positive | negative | null",
  "observed_direction": "positive | negative | null",
  "permutation_scheme": "free | block_differenced | stratified | cluster | paired | null",
  "split": "SplitRecord | null",
  "attacks": ["AttackResult"],
  "spec_hash": "str | null",
  "effect_interval": "EffectInterval | null",
  "power": "PowerNote | null",
  "outlier_warning": false,
  "evidence_score": 0.0,
  "score_components": {"s_q": 0.0, "s_e": 0.0, "s_r": 0.0},
  "failure_reason": "str | null"
}
```

Nested models:

- `SplitRecord` (`contracts/structure.py`): `method` (random_rows | by_time | by_entity |
  none), `seed`, `confirmation_fraction`, `n_exploration`, `n_confirmation`,
  `confirmation_digest`, `prior_looks`, `look_budget`.
- `AttackResult` (`contracts/attack.py`): `attack_id` A1-A7, `name`, `outcome` (survived |
  broken | not_run), `reason`, `original_effect`, `attacked_effect`, `n_rows`,
  `applicable`, `details`.
- `EffectInterval` (`contracts/interval.py`): `estimate`, `low`, `high`, `confidence`,
  `method` (row_bootstrap | entity_bootstrap | period_bootstrap), `n_resamples`.
- `PowerNote` (`contracts/power.py`): `effect_metric`, `detectable_effect`,
  `n_effective`, `unit` (observations | periods | entities), `alpha`, `target_power`.

Rules enforced by the models themselves:

- `verdict` is PASS iff `gate_outcome` is `supported`. FRAGILE, REFUTED, NEGLIGIBLE,
  INCONCLUSIVE and NOT_TESTABLE are all REJECT.
- Statistical fields are null exactly when the claim was never tested (`not_testable`);
  a tested claim carries all of them.
- `evidence_score` is present exactly for `supported` claims and only ranks; it never gates.
- Fields added in gateway v3 are optional with defaults, so older stored proofs load.

**Hard rule:** memory writes MUST check `verdict == "PASS"`
(`verification/memory_guard.py`). There is no other path in.

## 6. Evaluation (parked)

The planned four-condition ablation (A single LLM call; B agent loop, no gate; C agent
loop + LLM critic; D full PRAMANA) on a 40-dataset benchmark is **parked**. Results, if
ever produced, are to be framed as directional trends, not significance (n = 40, thin
power, disclosed). Famous datasets are excluded.

What exists: library code in `src/pramana/evaluation/` (conditions, metrics, run log,
report tables, planted truths). It has no runner or CLI and its ablation modules are
reachable only from `tests/unit/evaluation/`; conditions B and C raise
`NotImplementedError`. No benchmark results exist. The V2 evaluation plan is
`docs/EVALUATION.md` (also parked). What has actually been measured is in §11.

## 7. Demo

Tested tier: NHANES-style data (~500-2,000 rows, 8-15 columns) with real relationships
that should PASS and an injected false correlation that should REJECT. The injected decoy
must be one the proposer actually proposes, or it demonstrates nothing; the live DeepSeek
proposer has not reliably proposed it (`docs/evidence/DEEPSEEK_LIVE_TEST_LOG.md`), so the
stronger evidence for "rejects nulls" is the gate report card (§11) and
`tests/integration/test_gateway_e2e.py`.

Report tier: a retail or finance table with a time column, an amount and segments (for
example UCI Online Retail II rolled up to country x month) for Exact and Measured.
Demo data is built or downloaded locally into the gitignored `data/`; see
`scripts/build_demo_nhanes.py` and the `demo` block of `configs/analysis.yaml`.

## 8. Hard constraints

- Product-oriented deliverable: a working pipeline, not just a paper.
- Written report under 20% AI-generated and under 15% plagiarism (`AGENTS.md` §7).
- MIMIC-IV is forbidden. Use NHANES / NFHS-5 / other open data. No raw data in git.

## 9. Package map

All under `src/pramana/`.

| Package | One line |
|---|---|
| `contracts/` | Pydantic contracts every module imports (§5) |
| `common/` | runtime config, structured logging, Langfuse client, shared DeepSeek client, paths |
| `analysis/` | ingestion, cleaning, profiling, schema inference, Data reader, sectors, shape, claim filters, proposers |
| `analysis/computed/` | Exact tier: figures, story order, questions, code summary and checked reword |
| `analysis/measured/` | Measured tier: drivers, segments, anomalies, components, forecast, threshold, adjusted, leakage lint |
| `analysis/planner/` | planner engine: brief from exploration rows, validated `AnalysisSpec` |
| `analysis/workspace/` | agent engine: fixed tools and a bounded sandboxed Python workspace (sandbox off by default) |
| `analysis/hypotheses/` | rule-scan strategies and claim rendering |
| `analysis/benchmark/` | demo and benchmark dataset builders |
| `verification/` | the gateway: `gateway.py`, `admissibility.py`, `schemes.py`, `fdr.py`, `evidence.py`, `spec.py`, `looks.py`, `interval.py`, `power.py`, `refuter.py`, `memory_guard.py` |
| `verification/stats/` | the trust anchor: permutation, bootstrap, effect sizes, change, dependence, HMAC provenance |
| `verification/falsification/` | template generator (default) and DeepSeek generator with prompts |
| `verification/executor/` | sandbox runner and import policy |
| `verification/attacks/` | attacks A1-A7 on passing claims |
| `advisory/` | Explainer and Skeptic, after the gate |
| `chat/` | Ask tab: tools, guard, gateway hand-off, per-dataset ledger |
| `memory/` | ChromaDB store of PASS lessons, retrieval as hints; the only package that imports chromadb |
| `orchestration/` | LangGraph graph, nodes, run lifecycle, integration with each tier, Celery tasks |
| `api/` | FastAPI app, auth, dataset store, routes |
| `evaluation/` | parked ablation library (§6) |

Other top-level folders: `configs/` (every threshold, seed and limit: `verification.yaml`,
`analysis.yaml`, `v1.yaml`, `sectors/`), `web/` (UI), `tests/` (pytest), `scripts/`
(checks and calibration), `docker/`, `docs/` (index in `docs/README.md`).

## 10. Run and test

- Install: `python -m venv .venv`, `pip install -r requirements.txt`, `pip install -e .`,
  then `cd web && npm ci && npm run build`.
- Keys go in the ignored `.env` (copy `.env.example` without overwriting existing keys):
  `DEEPSEEK_API_KEY`, `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`,
  `PRAMANA_LANGFUSE_ENABLED=true`.
- Start: `python -m pramana --port 8080`, open http://127.0.0.1:8080. The first memory
  write downloads the MiniLM embedding model (about 79 MB) once.
- Check which tree the venv imports: `python -c "import pramana; print(pramana.__file__)"`.
- Engine and generator: `PRAMANA_ANALYSIS_ENGINE` (api | planner | agent | deterministic)
  and `PRAMANA_VERIFICATION_GENERATOR` (template | llm). `.env.example` and
  `docker/docker-compose.yml` currently set `llm`; see STATUS.md.
- Offline reference run: `PRAMANA_ANALYSIS_ENGINE=deterministic`,
  `PRAMANA_VERIFICATION_GENERATOR=template`, `PRAMANA_LANGFUSE_ENABLED=false`. Not
  DeepSeek acceptance evidence.
- Tests: `python -m pytest` (pyproject sets `pythonpath = ["src"]`). Count:
  `python -m pytest --collect-only -q | tail -1`. Lint: `python -m ruff check .`.
- Calibration (`scripts/calibration/`): `analyst_recall.py` (planted-fact recall of the
  Exact report), `gate_report_card.py` (false-positive rate per scheme, power, attack
  false-kill), `measure_effects.py`, `simulate_bands.py`, `check_demo_gate.py`.
  Live check: `scripts/check_deepseek_live.py`.

## 11. History and evidence

History:

1. Sep to 20 Oct 2026: V1 gateway (contracts, stats library, BH, gate, sandbox,
   generators, memory guard), proposer, orchestration and benchmark pilot; PRs #3-#24.
2. 20-21 Oct: V1 local product and dashboard (PR #25); DeepSeek replaces Gemma (PR #26).
3. 22 Oct: per-person scopes replaced by one project, scope and status (PR #27).
4. 23 Oct: V2 platform part 1: accounts, datasets, Data reader, workspace UI, chat,
   Skeptic and Explainer (PR #28).
5. 24 Oct: Measured tier, planner, valid nulls (schemes, split), attacks, findings UI
   (PR #29); gateway v3 design (PR #30).
6. 24-25 Oct: gateway v3 F1-F7 and S1-S8 (S9 parked) and the analyst layer (price/volume/
   mix, segment growth, customers, RFM, seasonality on 24+ months, story, questions, KNN,
   PCA, segment profiles, claim filters), merged together as PR #31.
7. 25 Oct: cleanup branch `chore/satya/cleanup-for-review` (docs, archive, lint); no PR yet.

Measured (each with its caveat):

- Planted-fact recall of the Exact report, six synthetic tables, seven planted facts:
  3 of 7 before the analyst layer, 7 of 7 after (`analyst_recall.py --top 8`). The
  tables and the figures that find the facts were written by the same person; it shows
  known facts are surfaced, not that unknown ones are found.
- Gate report card (`gate_report_card.py --reps 100`, 1,000 permutations, family of one,
  alpha 0.05, seed 20261024): null false-positive rate 0.080 (free shuffle), 0.060
  (block-differenced), 0.040 (stratified), 0.040 (cluster); power 0.970 (rho about 0.3,
  100 rows) and 1.000 (within-month link, 216 rows); attack false-kill 0.000 on one
  planted shape. Standard errors 0.02-0.03. Source: `docs/GATEWAY_V3_STATUS_AND_SIGNOFF.md` §4.
- BH is pinned against statsmodels in `tests/unit/verification/test_fdr.py`.

Not measured: BH on families of correlated claims (the report card uses families of one);
attack false-kill rate on real tables and on frames where A3, A4 and A6 can fire; a
gate-vs-no-gate planted-truth comparison; Measured-tier false-lift rate; run-to-run
variability of the planner.
