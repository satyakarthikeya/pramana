# Gateway v3: status, comparison and sign-off sheet

Prepared 2026-10-24 for the verification owner (P.P. Satya Karthikeya). One place to see
every finance gap (F1-F7) and every gateway step (S1-S9) side by side: what is built,
what was measured, what moves a verdict, and what needs your signature.

"Direction approved" means you agreed in chat on 2026-10-24. It is not a signature on the
code. Sign each row of section 5 after reading the diff; nothing here is signed for you.

## 1. Branches (stacked; nothing is pushed or merged)

```
fix/satya/finance-gaps            F1, F2, F4, F5, F6                      0f26157
 └ feat/satya/gateway-s1-wording  S1 wording + power note                 265f953
    ├ feat/satya/gateway-s2-report-card   S2 report card                  3ff3567
    └ feat/satya/gateway-s3-applicable    S3 applicable flag              606473b
       └ feat/satya/gateway-s5-interval   S5 effect interval              fc13b48
          └ feat/satya/gateway-s4-spec-hash   S4 plan fingerprint         bd417ab
             └ feat/satya/gateway-s7-look-ledger   S7 reuse count         d1ebd7b
                └ feat/satya/gateway-s8-refuter   S8 refuter agent        be97531
                   └ feat/satya/finance-f3-f7    F3 prompt, F7 roll-up    698122c
integration/gateway-v3 = the line above + S2 merged (used only for testing)
```

PR 29 (the earlier stack) is still open and unmerged; all of the above builds on it.

## 2. Finance gaps

| ID | Gap | Status | Moves a verdict? |
|---|---|---|---|
| F1 | Claims lost to model-written code refused by the column policy | built: vetted tests are the default | Possibly (p-values come from the vetted test) |
| F2 | Trend untestable on 36 months (18 < 20) | built: confirmation holds back what the trend minimum needs while 8 periods stay for exploration | Yes, for short series |
| F3 | Weak planner claims (latest month vs the one before) | built, prompt only | No (code validation unchanged) |
| F4 | No margin figure | built (Exact tier) | No |
| F5 | Single inflated row not listed | built (Exact tier) | No |
| F6 | No fiscal-year wording | built, from the table's own fiscal column | No |
| F7 | Models skipped on transaction tables | built: roll-up to period x entity, whole entities held out | No (Measured never reaches the gate) |

## 3. Gateway v3 steps

| Step | What it does | Status | Moves a verdict? |
|---|---|---|---|
| S1 | "Held up" / "not robust" / "not enough evidence" wording; power note on non-significant claims | built | No |
| S2 | Gate report card script + plumbing test | built; numbers in section 4 | No |
| S3 | `AttackResult.applicable`: separates "does not apply" from "could not run" | built | No (no attack added or removed; not-run counts as neither survived nor broken) |
| S4 | `ProofObject.spec_hash`; a result under a different seed or resample count than the frozen plan is refused | built | No |
| S5 | Percentile-bootstrap interval beside the effect, resampling the unit the null shuffles | built; none for block-differenced series | No (band rule unchanged, decision 2) |
| S6 | Vetted tests by default; `llm` stays selectable | built as part of F1; the existing agreement check still compares the two when `llm` is on | See F1 |
| S7 | Count of earlier runs on the same held-back rows, shown on the proof | built, disclosure only | No |
| S8 | Refuter: a model may suggest extra controls / subgroup columns; it can only add checks | built, OFF by default | No |
| S9 | Online FDR for chat | parked (decision 4) | |

## 4. What was measured, and what was not

**Gate report card** (`scripts/calibration/gate_report_card.py --reps 100`, real gateway,
vetted tests, 1000 permutations, a family of one claim, alpha 0.05, seed 20261024):

| Scenario | Rate | Standard error |
|---|---|---|
| Null: independent rows, free shuffle | 0.080 | 0.027 |
| Null: two random walks (block-differenced) | 0.060 | 0.024 |
| Null: shared season, many rows a month (stratified) | 0.040 | 0.020 |
| Null: label fixed per entity (cluster) | 0.040 | 0.020 |
| Power: rho about 0.3, 100 rows | 0.970 | 0.017 |
| Power: within-month link, 216 rows | 1.000 | 0.000 |
| Attack set wrongly breaking a true moderate effect | 0.000 | 0.000 |

Read with care: 100 replicates each. The 0.080 is 1.1 standard errors above 0.05, which
is consistent with a correct test but does not prove it; more replicates would tighten
it. These are single-claim families, so the Benjamini-Hochberg step and correlated claim
families (weakness W3 in the design) are NOT measured. Power is for two effect sizes
only. The attack false-kill rate is for one planted shape (not a real table).

**Live runs, real DeepSeek, planner engine, integrated stack:**

| Table | Before (this session) | Now | Runtime |
|---|---|---|---|
| NHANES demo (1,500 adults) | 3 PASS, 2 REJECT | 3 PASS, 2 REJECT, 0 unverified, memory holds the 3 PASS | 375 s |
| Synthetic financial-year (432 rows, planted effects) | degraded; 1 PASS, 6 REJECT | completed; 3 PASS, 2 REJECT (1 fragile, 1 inconclusive) | 236 s |

The planner proposes different claims each run, so the counts matching the baseline is
not a regression test of specific claims. The finance table is synthetic.

Things a reader should know from those runs:
- On the finance table the two group-difference PASSes survived only 3 of 3 *applicable*
  checks; four of the seven attacks do not apply to a group comparison. "Held up" rests
  on those three.
- The finance trend claim stayed inconclusive. Its power note says why: with 20 periods
  an effect below about 0.40 (Kendall tau-b) would often be missed. That is low power,
  not a bug.
- F3 worked in this run (no latest-month claim) but the planner still did not propose
  seasonality or a year-on-year test; the Exact tier reports those as figures only.
- Wall-clock rose (NHANES 282 s before, 375 s now, with other jobs running at the same
  time). The effect interval (up to 5000 resamples per passing claim) is the likely cost;
  not isolated.

**Tests:** the full suite on the integrated stack passed (1265 tests). The suite on the
merged analyst branch is recorded in the pull request. The effect interval is capped at 1,000
resamples (5,000 cost 15-20 s per passing claim). A live NHANES run with the real gate gave
3 verified and 3 rejected (one fragile: the HbA1c effect fell from +0.30 to +0.11 once age was
held fixed), in 259 s.

## 5. Sign-off sheet

"Direction" = approved in chat 2026-10-24. Tick "Code reviewed" after reading the diff.

| # | Change | Why it needs you (AGENTS.md) | Direction | Code reviewed | Signed |
|---|---|---|---|---|---|
| 1 | Vetted tests are the default gate generator; `llm` opt-in | section 2 role of the model; p-values | approved | [ ] | [ ] |
| 2 | AGENTS.md section 2 sentence amended to match | shared file, 8.7 | approved with #1 | [ ] | [ ] |
| 3 | Time-ordered split may hold back more than 50% (min_exploration_periods = 8) | split / statistics | approved (F2) | [ ] | [ ] |
| 4 | Wording and badges: HELD UP, NOT ROBUST, "not enough evidence" | wording of verdicts | approved | [ ] | [ ] |
| 5 | Contracts: ProofObject.power, .effect_interval, .spec_hash; SplitRecord.prior_looks / look_budget; AttackResult.applicable (all optional with defaults; old stored proofs load) | contracts, 8.7 | approved with the steps | [ ] | [ ] |
| 6 | Config keys: power_target, interval_confidence, min_exploration_periods, max_prior_looks, refuter_* (refuter off) | thresholds live in one file, 3.3 | approved | [ ] | [ ] |
| 7 | Refuter: a model suggests extra A3 controls / A4 subgroup columns; validated by code; can only add checks; off by default | model role, prime directive | approved in direction | [ ] | [ ] |
| 8 | Spec hash and drift refusal | statistics correctness | approved in direction | [ ] | [ ] |
| 9 | Planner prompt steering (F3) | analysis model prompt | approved | [ ] | [ ] |
| 10 | Chat control / online FDR (S9) | | parked, not built | | |

Invariants checked by tests in this stack: a tested claim that is not significant gets
no interval and attacks never run on it; a REJECT is never upgraded; a FRAGILE claim is a
REJECT and is never stored; a disabled, empty, failed or garbage refuter reply gives
exactly the default attack results; a result produced under a different seed or resample
count is refused; proofs written before these fields still load.

## 6. Not done / open

- S5: no interval for block-differenced (trend) claims; needs a block bootstrap of the
  changes.
- S7: a re-split on a new seed is not offered (a time-ordered split cannot be redrawn);
  chat claims are not counted in the ledger because they have no split.
- Attacks for period-change and seasonality claims: still "does not apply" for all seven.
- T5 (segment drove the change), T7 (model beats baseline), T8 (adjusted association) as
  tested claims; a chart for the new claim types.
- BH on correlated claim families and a real-data attack false-kill rate are unmeasured.
- Evaluation (P0) is parked. Docker was not run.
- The analyst layer (docs/ANALYST_LAYER_STATUS.md) does not change the gateway. A table above
  3,000 rows is now analysed with its trend claims left out (the Sen-slope memory ceiling is
  unchanged); trend tests on large tables would need a different method, which is for the
  verification owner to decide.
