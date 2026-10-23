# PRAMANA V2 — Implementation Plan

| | |
|---|---|
| Status | PROPOSAL, not approved. Nothing in it is built. |
| Written | 2026-10-23 |
| Applies to | **V2. Work starts after the 27 Oct 2026 review.** V1 is in code freeze from end of Mon 26 Oct (`SCOPE.md`); this plan touches nothing before then. |
| First step after the review | Replace `SCOPE.md` with a V2 scope derived from this file (today's §3 puts benchmark runs and bootstrap CIs out of scope; V2 needs both). |
| Amendment rule | This plan changes only by a dated entry in §13 with its reason. No phase starts work this file does not list. A future session that wants something not listed adds an amendment first, or does not do it. |

---

## 1. Why V2 exists (the measured problem)

Facts, each checked in the code on 2026-10-23:

1. **Three claim shapes only.** `admissibility.TESTABLE_CLAIM_TYPES` = correlation, group_difference, trend. Every PASS reduces to "A relates to B". An analyst finds the same in a minute.
2. **The analyst's tools are descriptive only.** `workspace/tools.py`: describe, compare_groups, relate, trend, missingness, scan_pairs, python. The sandbox ships OFF and allows numpy/pandas/math/statistics.
3. **The "falsification agent" does not falsify.** `falsification/prompts.py` restricts it to the two claim columns, no row filtering, one shuffle test. It writes the same single test as the deterministic template (`templates.py`). It never looks for another explanation.
4. **Free shuffles assume independent rows.** `stats/permutation.py` uses a plain `rng.shuffle` with no blocks or strata. On time-ordered or repeated-entity data (any financial year by month, any panel) this null is wrong and p-values come out too small. A random walk will look like a "significant trend".
5. **Selection is not counted.** `scan_pairs` and the hypothesis strategies rank many pairs, the top few are proposed, then tested on the SAME rows. `fdr.apply_bh` corrects only over the tested claims (`n_hypotheses_in_batch`); the exploration ledger's `examined` count never reaches `verification/`. That is double-dipping: the q-values are optimistic.
6. **Thresholds are mostly provisional.** `configs/verification.yaml`: only the `spearman_rho` floor is calibrated (one NHANES table); kendall, cliffs, epsilon² are conventions; `min_observations: 20` is a placeholder.
7. **Trend refuses tables above 3,000 rows** (`effect_size.MAX_SENS_SLOPE_OBSERVATIONS`, `tools.MAX_TREND_ROWS`), so most transaction tables cannot get a trend at all.

What is GOOD and stays: fail-closed everywhere, the vetted stats library with HMAC provenance, the gate's conjunction (`q < alpha AND |effect| >= floor AND direction`), score never gates, causal and universal wording refused before testing, reproducible seeds, PASS-only memory.

---

## 2. Frozen decisions (do not reopen without an amendment)

| # | Decision | Reason |
|---|---|---|
| D1 | Every statement the user sees carries one of three **evidence levels**: **Exact**, **Measured**, **Tested**. | Users can see why each one is trusted; nothing is called "verified" that was not tested. |
| D2 | **Exact** = deterministic arithmetic on the uploaded table, recomputed by code, shown with formula, columns, filters and row count. No uncertainty claimed. | Totals, growth, shares need no p-value; they need to be right and checkable. |
| D3 | **Measured** = a model or method with a measured error on data it did not see (held-out score, backtest error, stability), always against a baseline. No "real effect" claim. | ML and forecasts cannot be proven; their past accuracy can be measured honestly. |
| D4 | **Tested** = passed the gateway. Only Tested + PASS reaches memory. `memory_write ⟹ verdict == PASS` unchanged. | Prime directive (`AGENTS.md` §0). |
| D5 | **Exploration and testing use different rows.** The run splits the table once (seeded, logged): an *exploration* part, and a *confirmation* part only the gateway and attacks see. Time data splits by time; panel data splits by entity. The USER sees Exact and Measured computed on the full table; the PLANNER, and anything promoted to a Tested claim, sees only versions computed on the exploration split. A test asserts the planner's input digest contains no confirmation rows. | Fixes fact 5 without inflating the BH family to every scanned pair. Standard sample-splitting; the cost is power, which the benchmark measures. |
| D6 | **The null must respect the data's dependence.** Free shuffle only for independent rows. Repeated entities → stratified (within period) or cluster (entity-level) permutation. **Time series: test on first differences, never on levels**, with block permutation of the differenced series; if a unit-root screen still fires on the differences, or the series is shorter than the per-type minimum length, the claim is NOT_TESTABLE. If no valid null exists for a shape, NOT_TESTABLE. | Fixes fact 4. Block permutation on non-stationary levels does not control FPR on random walks; differencing does. Fail-closed rather than a wrong p-value. |
| D6b | **Short series are not testable, by design.** One financial year of monthly data (12 points; 6 per split half) is below every tested minimum. It gets Exact and Measured (as far as their own minimums allow) and its Tested section says "too few periods to test". Per-type `min_series_length` keys in config. | Honest: 12 points cannot carry a valid dependence-aware null. Better to say so than to show a meaningless p-value. |
| D7 | **ML from a closed menu in trusted code.** The LLM picks target, features, model and split from the menu through a structured spec. It writes no model code. | Leakage and tampering live in free-form model code. sklearn also breaks the current sandbox. |
| D8 | **The agent's Python sandbox stays descriptive.** It may compute leads for exploration on the exploration split; its outputs are never shown as findings and never reach the gate. No scipy/sklearn inside it. | The user asked that the agent can use Python: it can, for exploring. It cannot produce evidence. |
| D9 | **Falsification attacks are a one-way ratchet.** They can only lower a verdict, never raise it. They downgrade on **effect consistency** (sign flip, or shrinking past a configured fraction), never on subgroup significance. Every attack must show, on planted data, that it can fail. | Attacks add rigor without adding false discoveries; subgroup p-values fail real findings by low power alone. |
| D10 | **No causal or universal wording, anywhere**, including Explainer and narrative. "Driver" means "accounts for X% of the change / of the model's held-out skill in this data", never "causes". | Observational data. |
| D11 | **Every number in narrative text matches a computed number** (extends today's Explainer guard to the whole report), or the sentence is dropped and the fallback shown. | Models propose, code decides. |
| D12 | **The dataset-shape classifier decides which analyses run.** No forecast without a time column, no panel test without an entity column, etc. | Prevents nonsense analyses. |
| D13 | **Thresholds live in config only** (`AGENTS.md` §3.3). New keys added to `configs/verification.yaml` (gate, attacks) or `configs/analysis.yaml` (exact/measured tiers). | Existing rule. |
| D14 | **DeepSeek remains the only generative provider; every call is traced in Langfuse; fail closed without it.** The deterministic path stays as the offline mode. | `AGENTS.md` §2. |

## 3. Non-goals for V2 (do not build)

- Causal inference of any kind (DAGs, instruments, "uplift" claims).
- LLM-written model code, or any LLM-computed number.
- AutoML / hyperparameter search beyond the small fixed grids in §6.
- Deep learning, LLM embeddings as features, text columns as model inputs.
- Multi-user scaling, more than one run at a time, cloud deployment.
- Real-time / streaming data. Joins across multiple uploaded tables.
- Categorical-vs-categorical tested claims (stays out until a calibrated Cramér's V band exists).

---

## 4. Architecture (one pipeline, seven stages)

```
upload
  └─ 1 PROFILE    ingestion, cleaning, schema (exists) + SHAPE CLASSIFIER (new)
  └─ 2 SPLIT      exploration / confirmation split by shape (new, D5)
  └─ 3 EXACT      deterministic analyses on the FULL table (new)          -> Exact
  └─ 4 MEASURED   closed-menu ML + forecast, own CV inside (new)           -> Measured
  └─ 5 PLAN       DeepSeek planner: picks analyses + proposes claims       (extends agent)
                  from exploration split; structured output only
  └─ 6 GATE       gateway on confirmation split: dependence-aware nulls,   -> Tested
                  one BH family, effect band, direction (extends gateway)
       └─ 6b ATTACK  falsification attacks on every PASS, one-way ratchet (new)
  └─ 7 REPORT     narrative from numbers (number-matched), proof cards,
                  rejected list, evidence level on every line              (extends advisory/api/web)
memory <- only Tested PASS that survived attacks
```

Why Exact runs on the full table: arithmetic does not overfit, so splitting it only loses information. Why Measured runs its own CV: it already holds data out by design.

### 4.1 Dataset-shape classifier (stage 1)

Deterministic, from `SchemaProfile` (roles: numeric, categorical, ordinal, datetime, id_like).

| Shape | Rule (sketch; exact rules are a Phase 2 test spec) | Valid nulls | Example |
|---|---|---|---|
| `cross_section` | no datetime/ordinal-time column, no repeated id | free shuffle | survey, NHANES |
| `time_series` | one time column, ≤ 1 row per time point (after optional aggregation) | block permutation | monthly P&L |
| `panel` | time column + id-like/entity column repeated across time | within-entity / cluster permutation | sales per region per month |
| `transactions` | time column, many rows per time point, optional entity | aggregate to a period series or panel first, then as above | invoices, ledger lines |

**Short series.** A `time_series` with fewer periods than the tested minimum (e.g. 12 months) gets Exact items, a Measured forecast only if it has ≥ 2 full seasonal cycles (otherwise trend-only or seasonal-naive with "too short to model seasonality"), and no Tested claims. For a `transactions` table, daily aggregation is tried first so longer series become testable.

The classifier output (shape, time column, entity column, period granularity) is recorded in the run and shown to the user ("We treated this as monthly data per region"). The user can correct it in the UI (Phase 7); a correction re-runs the pipeline.

---

## 5. Analysis catalog — what we analyse and how each is verified

Legend: **E** Exact, **M** Measured, **T** Tested. "Attacks" refers to §7.

### 5.1 Exact tier (stage 3) — `analysis/computed/`

| ID | Analysis | Shapes | Method | Shown as | Known-answer test |
|---|---|---|---|---|---|
| E1 | Column summary | all | count, missing, mean, median, IQR, top levels | table | hand-computed frame |
| E2 | Totals & aggregates per period | ts, panel, tx | sum/mean by period | numbers + chart | planted totals |
| E3 | Period-over-period change (YoY, QoQ, MoM) | ts, panel, tx | (cur − prev) / prev; absolute and % | "Revenue +14.2% (₹X → ₹Y)" | planted growth |
| E4 | Variance decomposition | panel, tx, cross (by category) | additive: Δtotal = Σ Δsegment; share of change per segment; for ratios a price/volume (mix) split | waterfall | planted "region A drives growth" |
| E5 | Concentration | all with a value + category | top-k share, Pareto (80/20), HHI | "Top 10% customers = 63% of revenue" | planted Pareto |
| E6 | Segment ranking | all with category | per-segment total, mean, margin, growth; rank | table | planted segment |
| E7 | Ratios & margins | when numerator/denominator columns are identified by the planner and confirmed by the user | ratio per period/segment | numbers | planted margin |
| E8 | Robust outliers / anomalies (univariate) | all numeric | robust z = (x − median) / (1.4826·MAD); flag above configured cutoff; per period for ts | list + reason | planted spike |
| E9 | Seasonality profile | ts, panel with ≥ 2 full cycles | mean by month-of-year / weekday, normalised to overall mean | heat strip | planted December peak |
| E10 | Trend shape (descriptive) | ts | rolling mean, Theil–Sen slope in units/period | line | planted slope |
| E11 | Data-quality findings | all | duplicates, impossible values (negative counts), gaps in periods, constant columns, id-like columns | warnings | planted defects |
| E12 | Correlation overview (descriptive) | numeric pairs | Spearman matrix, existing `data_overview` | heatmap | exists |
| E13 | Principal components (descriptive) | ≥ 3 numeric columns, cross/aggregated | standardise, PCA, variance explained, top loadings; **stability** via bootstrap of loadings and **parallel analysis** vs shuffled data → only components beating shuffled data are shown | scree + loadings | planted 2-factor structure |

Every Exact item stores `{formula, columns, filters, n_rows, value}` and the UI renders "show your work" from it. A **recomputation checker** re-derives every Exact number shown in narrative text (D11).

### 5.2 Measured tier (stage 4) — `analysis/models/` (closed menu, trusted code)

All models: sklearn `Pipeline` (impute → scale/encode → model), all preprocessing fitted on training folds only; seed from config and logged; leakage lint first (§5.2.1); always a baseline; the headline number is **lift over baseline on held-out data**, with a fold-to-fold spread.

| ID | Task | Menu | Split | Baseline | Headline | Stability shown |
|---|---|---|---|---|---|---|
| M1 | Driver ranking (regression target) | Linear (ridge), Random Forest, Gradient Boosting, **SVR** | KFold (cross) / GroupKFold (panel) / TimeSeriesSplit (ts) | mean predictor | held-out R², ΔR² vs baseline; permutation importance on held-out folds, grouped for correlated features (|ρ| > configured cutoff) | importance rank agreement across folds |
| M2 | Driver ranking (class target) | Logistic, RF, GB, **SVC** | same | majority class | balanced accuracy / AUC lift | same |
| M3 | Adjusted association | Linear/logistic with listed controls | same | model without the variable | partial effect + ΔR² when the variable is added | sign agreement across folds |
| M4 | Segments | KMeans (k from a fixed small range, chosen by silhouette on train) | bootstrap | shuffled-data clustering | silhouette vs null; bootstrap ARI stability | ARI ≥ configured cutoff else "no stable segments" |
| M5 | Multivariate anomalies | IsolationForest | n/a | robust-z (E8) | rows flagged by both vs one; what flagged rows share (E1 on them) | rank stability across seeds |
| M6 | Forecast | seasonal-naive (baseline), exponential smoothing (Holt-Winters, statsmodels), linear trend + seasonal dummies | rolling-origin backtest | seasonal-naive | MAPE/MASE vs baseline on backtest; prediction interval from backtest residuals | interval coverage on backtest |
| M7 | Threshold / non-linear shape | piecewise-linear (one breakpoint, grid) vs linear | same as M1 | linear | ΔR² held-out; breakpoint with bootstrap range | breakpoint range |

Fixed grids only (e.g. RF depth ∈ {3, 6, None}); the full grid size is recorded as "models tried". **Nested CV** whenever a grid is searched, so the reported score is not the tuned score.

A Measured result is shown as "**model beats baseline by X on data it did not see (± spread)**". It is never called a finding. If lift ≤ configured floor: "No model beat the baseline" — that is a result, shown.

#### 5.2.1 Leakage lint (runs before any model; refuses the spec on a hit)

- id-like columns (schema role `id_like`, or unique per row) → excluded.
- near-deterministic target proxies: any single feature with held-out R²/AUC above configured cutoff on its own → excluded and reported ("`net_profit` is revenue − cost, so it was not used to predict revenue").
- accounting identities: a feature that sums/differences to the target exactly (checked numerically) → excluded.
- post-outcome time columns (timestamps after the target's period) → excluded.
- a suspiciously perfect score (held-out ≥ configured cutoff) → result withheld, shown as "too good to be true; check for leakage".

### 5.3 Tested tier (stage 6) — the gateway

Existing claim types, fixed for V2:

| ID | Claim | Shapes | Null & permutation scheme | Metric (band) | Attacks |
|---|---|---|---|---|---|
| T1 | correlation | cross | free shuffle of Y vs X | spearman_rho (0.10 / 0.50) | A1 A2 A3 A5 |
| T1p | correlation | panel | shuffle within time period (strata) | spearman_rho | A1 A2 A3 A4 |
| T2 | trend | ts | the claim "Y tends to rise over time" is tested as "the mean first difference of Y is not zero": statistic = Kendall tau-b of Y vs time; null built by **circular-block sign-flipping of the first differences** (block length from config, default ⌈n^(1/3)⌉), re-integrating, recomputing tau. Refuse if n < `min_series_length.trend` | kendall_tau_b (0.07 / 0.35) | A2 A6 |
| T2p | trend | panel / tx | aggregate to period series per entity, test the pooled per-entity tau with entity-level permutation of signs | kendall_tau_b | A2 A4 A6 |
| T3 | group_difference | cross | shuffle labels, sizes kept | cliffs_delta / epsilon² | A1 A2 A3 A5 |
| T3p | group_difference | panel | shuffle labels at entity level (cluster permutation) | same | A1 A2 A4 |

Trend > 3,000 rows: Theil–Sen is O(n²). For `tx`, trend runs on the aggregated period series (small n) — this removes the limit for finance tables. For a genuine long series, Sen's slope on a seeded random subsample of pairs (size from config), recorded as such.

New claim types (Phase 8, each needs the verification owner):

| ID | Claim | Null | Metric |
|---|---|---|---|
| T4 | period change ("Q3 higher than Q2") | block-bootstrap CI on the difference excludes 0 → p via inverted CI; or permutation of period labels within blocks | relative change, band in config |
| T5 | segment drove change ("region A accounts for > X% of growth") | bootstrap of rows within periods → CI on the share | share of change |
| T6 | seasonality ("month-of-year effect exists") | permute whole cycles (years) or detrend + shuffle month labels within year | epsilon² across months |
| T7 | model beats baseline (from M1/M2, refit on the exploration split's choice, tested on confirmation) | `permutation_test_score`-style: permute target, re-run the WHOLE CV pipeline. B may be below 10,000 for cost but must satisfy **B ≥ m_max/α − 1** (`statistics.m_max` = largest family a run may have; at α = 0.05, m = 40 → B ≥ 799), else the claim is NOT_TESTABLE because it could never pass BH | ΔR² / AUC lift |
| T8 | adjusted association (from M3) | Freedman–Lane permutation (permute residuals of reduced model) | partial ρ / standardized β |

All T-claims from one run go into ONE BH family, as today. M-results are never in the family. The planner may promote an M-request to a T7/T8 claim only from its exploration-split version (D5); the claim is then tested once on the confirmation split.

---

## 6. The planner (stage 5) — what DeepSeek does

Extends `analysis/workspace/agent.py`; same budget and trace rules.

Input: schema, shape classification, and Exact / Measured / tool results computed on the **exploration split only** (D5). The full-table versions go to the user, never to the planner.

Output (structured, Pydantic, validated; nothing else is accepted):

```
AnalysisSpec:
  shape_confirmation: shape + time_col + entity_col   (may only confirm or flag; code decides)
  measured_requests:  [{task: M1..M7, target, features[], controls[], reason_code}]
  claims:             [{claim_type: T1..T8, variables, direction, reference_group}]
  narrative_focus:    [ids of Exact/Measured/Tested items to lead the summary]
```

Rules:
- Targets/features must exist and pass the leakage lint, else that request is dropped and recorded.
- At most N measured requests and M claims per run (config).
- The planner never sees the confirmation split.
- Claim text is still rendered by code from templates.
- The narrative writer (Explainer extended to the whole report) uses only numbers present in the run's results (D11).

---

## 7. The falsification tool (stage 6b) — "try to prove it wrong"

A new component `verification/attacks/`, separate from the existing generator. Today's generator keeps its job (one test per claim); attacks run AFTER the gate, only on PASS claims, on the **confirmation split**.

### 7.1 How it works

1. **Attack planner (DeepSeek, structured).** For each PASS finding, picks attacks from the menu and their parameters (which column to control, which split). It may also propose "this other column might explain it" — only names of existing columns. It writes no code.
2. **Deterministic attacks always run** regardless of the planner (A1, A2 for every claim; A4/A6 by shape). The planner adds A3/A5/A7 targets. So a lazy planner cannot weaken the attack set.
3. **Code executes** each attack via vetted functions in `pramana.verification.stats` / `verification/attacks/` and records the result with provenance.
4. **Ratchet.** Any attack outcome `BROKEN` → verdict becomes REJECT with outcome `FRAGILE` (new `GateOutcome`) and the attack named as the reason. No attack can turn REJECT into PASS. Memory receives only findings with zero `BROKEN`.
5. **User sees:** "Survived 5 of 5 attacks" or "Did not survive: effect reverses in region North (n = 412)". Attacks that could not run (precondition, n) are shown as "not run: reason", never as survived.

### 7.2 Attack menu

| ID | Attack | Precondition | Procedure | BROKEN when (config keys) | Must catch (planted) | Must not kill (planted) |
|---|---|---|---|---|---|---|
| A1 | Outlier robustness | always | drop top/bottom `attacks.trim_fraction` by each variable; recompute effect | sign flips OR \|effect\| < `shrink_fraction`·original | effect created by 3 extreme points | true moderate effect with heavy tails |
| A2 | Split-half replication | n ≥ 2·`min_subgroup_n` | split confirmation rows in two (time halves for ts/panel, random for cross); effect in each | sign differs between halves OR either half below `shrink_fraction` | effect present only in last quarter | stationary true effect |
| A3 | Third-variable control | a candidate control column exists | partial rank correlation / stratify by control quantiles; recompute effect | \|partial\| < `shrink_fraction`·original | planted confounder Z→X, Z→Y | true X→Y with an unrelated Z |
| A4 | Subgroup consistency (Simpson) | categorical with ≥ 2 levels each ≥ `min_subgroup_n` | effect within each level | sign reverses in a level holding ≥ `subgroup_weight_floor` of rows, OR pooled sign opposite to weighted within-level sign | Simpson reversal | homogeneous effect |
| A5 | Alternative statistic | always | the other family (Pearson vs Spearman; Hedges g vs Cliff's δ; OLS slope vs Sen) | signs disagree | rank effect driven by ties/coding | true linear effect |
| A6 | Detrend / spurious time | ts, panel | first-difference both series (or remove each one's trend) and recompute | \|effect\| < `shrink_fraction`·original | two independent random walks | two series that truly co-move in changes |
| A7 | Leakage / identity | numeric pair | check exact/near-exact identity (Y = aX + b, sums) | identity found | net = revenue − cost pair | true correlated pair |

Attack thresholds (`trim_fraction`, `shrink_fraction`, `min_subgroup_n`, `subgroup_weight_floor`) are new config keys in `configs/verification.yaml` under `attacks:`, PROVISIONAL until calibrated in Phase 5.

### 7.3 Why this is sound

- One-way ratchet → attacks never increase the false-discovery COUNT; they can only cost power. (Removing true discoveries can raise the false-discovery PROPORTION, so FDP is measured after attacks too.)
- **Joint false-kill is the gate, not per-attack.** Seven attacks at 10% each would kill about half of true findings (0.9⁷ ≈ 0.48 survive). Thresholds are calibrated so the WHOLE attack set applied to a true finding kills it ≤ 15% of the time, while each attack keeps ≥ 0.80 power on its planted case.
- Consistency, not significance → a small subgroup is not punished for having fewer rows; it is punished only for pointing the other way or collapsing.
- Every attack has a planted case it must catch and a planted truth it must spare. An attack with power < target on its planted case is not shipped.
- Attacks run on the confirmation split, so the planner's choices cannot be tuned on the data they are judged on.

---

## 8. How we prove the platform works (benchmark)

Extends `src/pramana/evaluation/` (do NOT delete it; it is the measurement harness).

### 8.1 Planted suites

| Suite | What is planted | Measures |
|---|---|---|
| S0 null-cross | shuffled real extract, no injections (exists) | FPR of the gate |
| S0-rw | pairs of independent random walks; single random walks vs time | FPR of trend/correlation on time data |
| S0-panel | entity effects only (each entity has its own level), no true X–Y | FPR on panel data |
| S1 pairwise | monotonic, shift, trend (exists) | recall, precision |
| S2 confounder | Z→X, Z→Y, no X→Y | confounder rejection (A3 + M3) |
| S3 Simpson | within-group effect opposite to pooled | A4 power |
| S4 interaction | effect only in a subgroup | M1/M7 recall |
| S5 joint drivers | 3 weak predictors jointly predicting Y | M1 driver recovery (top-k) |
| S6 threshold | step change at a planted breakpoint | M7 breakpoint recovery |
| S7 leakage | target proxy and accounting identity columns | leakage-lint recall |
| S8 finance | two variants: **S8a** one year monthly × region (the user's real case: Exact must recover growth, driver region, spike; Tested must say "too few periods"); **S8b** three years daily × region (Exact + Measured forecast/seasonality + Tested trend reachable). Planted: growth, one region driving it, an expense spike, December seasonality, one random-walk column | recall of planted facts per tier; S8a also checks that nothing is falsely Tested |
| S9 clusters | k planted clusters; and a no-cluster control | M4 stability vs null |

### 8.2 Real-data controls

- Positive controls on NHANES/NFHS-5 (licence-checked, `AGENTS.md` §6): literature relationships (age ~ systolic BP, BMI ~ HDL already used).
- Negative controls: shuffled outcome column → nothing should PASS.
- Split-half replication: run on one half, check the other.

### 8.3 Targets (exit gates use these)

| Metric | Target |
|---|---|
| All-null suites S0, S0-rw, S0-panel: fraction of DATASETS with ≥ 1 PASS (FWER; BH controls it when every hypothesis is null) | ≤ α (0.05), upper binomial 95% bound reported, ≥ 200 datasets |
| Mixed suites: mean false-discovery proportion (FDP) | ≤ α, before AND after attacks |
| p-value calibration under null | KS test vs uniform not rejected at 0.01 |
| Confounder rejection (S2) | ≥ 0.90 |
| Attack power on its planted case | ≥ 0.80 each |
| Joint false-kill of the full attack set on planted truths | ≤ 0.15 |
| Finance recall S8a (Exact facts) | ≥ 3 of 3 on ≥ 90% of datasets; 0 Tested claims |
| Finance recall S8b (all tiers) | ≥ 4 of 5 facts on ≥ 90% of datasets |
| Leakage-lint recall (S7) | 1.00 on identities, ≥ 0.90 on proxies |
| Reproducibility | identical numbers, same seed, 100% |
| Narrative number faithfulness | 100% (mechanically enforced) |
| Power cost of D5 split | reported, not gated (S1 recall before vs after) |

### 8.4 Ablation table (the capstone evidence)

Same datasets, same seeds: (a) V1 as is → (b) + dependence-aware nulls + split → (c) + Exact → (d) + Measured → (e) + attacks → (f) full. Columns: FPR, recall per suite, finance recall, confounder rejection. Built by `evaluation/report_tables.py`.

---

## 9. Phases

Each phase: its own branch `feat/<owner>/<task>` from the previous phase's branch or `main` (§8.2), its own PR, tests written FIRST (they are the spec; forward references stay red), full suite green, exit gate met with numbers in the PR. Stop after each phase.

| Phase | Goal | Main files | Contract / config changes | Exit gate | Sign-off |
|---|---|---|---|---|---|
| **P0 Baseline** | Suites S0-rw, S0-panel, S2, S8 + runner; score V1 as is | `evaluation/planted.py` (+ new generators module), `evaluation/conditions.py`, `configs/evaluation.yaml`, `scripts/` | evaluation config only | Baseline table produced and committed; expected: FPR > α on S0-rw | verification owner (it reports on the gate) |
| **P1 Valid nulls** | D6 differencing + block sign-flip / stratified / cluster permutation; D5 split; trend on aggregated series; `min_series_length` | `verification/stats/permutation.py`, `templates.py`, `prompts.py`, `executor/policy.py`, `gateway.py`, `orchestration` split hook | new `PermutationScheme` in contracts; proof object records scheme + split; `verification.yaml: split, block, min_series_length, m_max` keys. **Sandbox rule change:** generated code may also read the run's declared time/entity column (today: only the two claim columns) | S0-rw and S0-panel FWER ≤ α; S1 recall drop reported | verification owner (§8.10: p-values AND sandbox rule) |
| **P2 Shape + Exact** | §4.1 classifier, E1–E13, recomputation checker | `analysis/shape.py`, `analysis/computed/*`, `api/models.py` (`computed` field), `api/service.py` | new `ComputedAnalysis` payload; `analysis.yaml: computed` keys | S8 Exact facts (growth, driver region, spike, seasonality) recovered ≥ 90% | analysis owner; AGENTS.md D1–D3 wording added as a NEW section at the end before §9 |
| **P3 Measured** | M1–M7, leakage lint | `analysis/models/*`, `requirements/runtime.txt` (+scikit-learn, statsmodels) | `MeasuredResult` payload; `analysis.yaml: models` | S5/S6/S7/S9 targets; S8 forecast beats seasonal-naive or says so | dependency note in commit (§1.4) |
| **P4 Planner** | §6 AnalysisSpec, budgets, narrative from all tiers | `analysis/workspace/agent.py`, `advisory/explainer.py` | `AnalysisSpec` model | Planner never reads confirmation split (test); 100% number faithfulness | analysis owner |
| **P5 Attacks** | §7 A1–A7, ratchet, `FRAGILE` outcome | `verification/attacks/*`, `gateway.py`, `contracts/enums.py`, `proof_object.py` | `GateOutcome.FRAGILE`, `AttackResult` in proof object; `verification.yaml: attacks` | each attack ≥ 0.80 power; joint false-kill ≤ 0.15; S2 confounder rejection ≥ 0.90; FDP after attacks ≤ α | verification owner (verdict rule change) |
| **P6 UI** | summary → Exact (show your work) → Measured (vs baseline) → Tested proof cards with attacks → rejected; evidence-level badges; shape correction | `web/src/*` (load `pramana-ui` skill first) | none | acceptance journey on S8 file and NHANES demo | UI owner |
| **P7 New tested claims** | T4–T8 | `verification/stats/*`, `templates.py`, `admissibility.py` | new `ClaimType`s, metrics, bands | each new type: FPR ≤ α on its null suite, power reported | verification owner |
| **P8 Ablation + docs** | §8.4 table, limitations, README | `evaluation/report_tables.py`, docs | none | table reproducible from one command | team |

Order rationale: measure first (P0); fix the gate before trusting anything new (P1); Exact gives the biggest user-visible jump with the least statistical risk (P2); Measured next (P3); planner once there is something to plan (P4); attacks once findings exist on valid nulls (P5); UI when payloads are stable (P6); new tested types last because each one is a new null to defend (P7).

---

## 10. Decisions for the user

1. **Who signs off §8.10 items?** Module headers name P.P. Satya Karthikeya as verification owner and the git user is `satyakarthikeya`. Confirm that is you, so P0/P1/P5/P7 sign-offs are yours.
2. **Approve this plan as the V2 scope**, to be turned into the new `SCOPE.md` after the 27 Oct review.
3. **Dependencies:** scikit-learn and statsmodels into `requirements/runtime.txt` at P3.
4. **D5 split** costs power (fewer rows to test on). Accept, with the cost reported in P1? The alternative is counting every scanned pair in the BH family, which costs more.
5. **The DeepSeek falsification generator** writes the same test as the template. Keep it (it is the D1 design) or make the template the default and drop a model dependency? Measured in P0 either way.

## 11. Simplification track (optional, separate from the build)

Survey on 2026-10-23: ~19.4k src LOC, ~13k test LOC, ~4.6k web LOC. Each item needs its owner's decision; none is a plan step.

| Candidate | LOC | Idea | Constraint |
|---|---|---|---|
| orchestration/ | 1851 | ~10 adapter files → one pipeline function | Celery path, owner |
| config layers | ~960 + 10 YAMLs | one settings class | shared config (§8.7) |
| chat/ + Ask.tsx | 1451 + 350 | shrink to ~400 | requested 21 Oct |
| advisory/ small files | ~200 | merge | — |
| falsification LLM generator | ~410 | template as default | decision 10.5 |
| memory/ + chromadb | 659 | keep | protects §0 |

`evaluation/` is not a candidate.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Split halves power; fewer PASS | Report it (P1 gate); Exact/Measured tiers carry most of the value anyway |
| Block length choice changes p-values | Fixed rule in config, logged in proof, benchmarked on S0-rw |
| Permutation of whole CV (T7) is slow | Lower B for T7 with recorded floor; run in worker |
| Attacks kill true findings | Joint false-kill gate ≤ 0.15 across the whole set; thresholds calibrated in P5 |
| User's own example (one financial year, monthly) gets no Tested findings | Stated up front (D6b); Exact + Measured carry it; daily aggregation tried for transaction tables |
| Shape classifier wrong | Shown to user, user can correct, re-run |
| Planner leaks confirmation data | Split enforced in code, test asserts planner input excludes it |
| Narrative overclaims | D10 vocabulary screen + D11 number match, fallback to code sentence |
| Scope creep | §2 frozen decisions, §3 non-goals, §13 amendment rule |

## 13. Amendments

| Date | Change | Reason |
|---|---|---|
| 2026-10-23 | Added §8.5 answer-accuracy benchmark (PRAMANA-QA + InfiAgent-DABench slice). | User asked for a professional benchmark that scores whether each output is correct, like DABench. |
| 2026-10-23 | Evaluation (§8, §8.5, datasets) moved to `docs/EVALUATION.md` and PARKED. | User: "keep evaluation afterwards"; build the analysis platform first. |
| 2026-10-23 | **Phase order: P2 (shape + Exact) now runs FIRST**, before P0 and P1. P1 is still required before any NEW Tested claim on time-ordered data. | P2 does not touch the gate, so it is safe to build before the gate fix; the user wants the analysis platform first. |
| 2026-10-23 | **P2 interim exit gate:** known-answer tests on a hand-built finance year (12 months × regions) and a small health fixture (with survey weights), instead of the parked S8 suite. The S8 gate is re-applied when evaluation resumes. | S8 generator is parked, so the original gate cannot be met yet. |
| 2026-10-23 | Added §14 sector packs; first two sectors are **finance** and **health**. | User: build for two sectors so a new sector is easy to add. |

## 14. Sector packs (added by amendment, 2026-10-23)

- A sector pack is **YAML only** (`configs/sectors/<sector>.yaml`): vocabulary (column-name patterns → semantic roles), known identities, which core analyses to enable and their parameters, weight-column rules, wording notes. **No code in packs**, so a new sector cannot add unreviewed code.
- Sector detection is **deterministic** (vocabulary match score), falls back to `general`, and the user can override it. No model call.
- Health vocabulary reuses `analysis/codebook.py` (NHANES labels); it is not duplicated.
- **Survey weights:** health estimates use the detected weight column (e.g. `WTMEC2YR`, `WTINT2YR`) when present; without one, every figure is labelled "share of this sample, not a population estimate".
- A new analysis TYPE is core code (reviewed, tested); a new SECTOR only selects and parameterises existing types. A sector that needs a new Tested claim type goes through §8.10.
- First slice (P2): shape classifier; Exact analyses E2 E3 E4 E5 E6 E8 E9 (≥ 2 full cycles) E11; health prevalence, rates and weighted estimates. E1/E12 already exist (overview, brief). E7 and E13 deferred. pandas/numpy only. `computed` is shown to the user and is NOT passed to the proposer, agent or chat (D5).

## 8.5 Answer-accuracy benchmark (added by amendment, 2026-10-23)

Planted suites (§8.1) score the GATE. This scores the WHOLE PLATFORM's answers against gold answers, item by item.

**Item format** (`data/eval/qa/<suite>/items.jsonl`, manifest committed):
```
{id, dataset_id, question, answer_format, gold, tolerance, expected_level: E|M|T|REFUSE, category, source}
```
- `answer_format` follows DABench's `@name[value]` convention, so answers are machine-checkable.
- `gold` for synthetic and real items is computed by an independent reference script (pandas, written separately from `analysis/computed/`), never by the platform.
- `tolerance`: exact for counts/labels, relative 1e-6 for arithmetic, a stated band for Measured items (e.g. "lift > 0", "top-3 contains region_A").

**Suites:**

| Suite | Items | What it checks |
|---|---|---|
| QA-dabench | InfiAgent-DABench closed-form questions, famous CSVs (Titanic etc.) removed | descriptive/Exact accuracy; external comparability. Regression slice only (public, possibly in DeepSeek training data). |
| QA-finance | ~300 questions over S8a/S8b and Online Retail II ("YoY growth of region A?", "which month is the spike?", "top-10% customer share?") | Exact and Measured correctness on the user's main use case |
| QA-tested | questions whose gold is a planted truth ("is X related to Y?" → yes/no from the truth table) | Tested tier: precision/recall per item |
| QA-refuse | questions the platform MUST decline: causal ("does X cause Y?"), too few points (12-month significance), leakage targets, nonexistent columns | honesty: correct-refusal rate. An answer here is scored WRONG even if the number is right. |

**Scoring:** per-item correct/incorrect; accuracy per suite and per category; DABench's three metrics (accuracy by question, by sub-question, proportional) on QA-dabench; refusal precision/recall on QA-refuse; confidence intervals by bootstrap over datasets. One command produces the table; results committed per phase.

**Targets:** QA-finance Exact ≥ 0.95; QA-refuse correct-refusal ≥ 0.95 with ≤ 0.05 false refusals on answerable items; QA-dabench reported against V1 baseline (no fixed target).

**Phase:** QA-dabench + QA-refuse join P0 (baseline V1); QA-finance from P2; QA-tested from P1.
