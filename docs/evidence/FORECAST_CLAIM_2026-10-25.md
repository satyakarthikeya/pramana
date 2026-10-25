# Forecast claims, 2026-10-25: the gateway tries to prove a forecast wrong

Status: measurement note for the verification owner (P.P. Satya Karthikeya), written under his
delegation of 25 October 2026 (build the claim type behind a config flag that defaults OFF; he
decides the default after reading these numbers). **`claims.forecast_enabled` ships `false`.
Nothing in this note is signed by the owner.** Section 8 says what the numbers say about the
default.

All data are **synthetic and author-built**: series I planted with known truth, run through the
repo's own code. They show how the new claim behaves on those shapes. They do not show how often
it is right on a real table, and nothing was tuned on a real table.

## 1. What was built

A new claim type, `forecast`: "A forecast of `<column>` by `<method>` beats `<a seasonal-naive |
a last-value>` forecast, measured on periods it did not see, over `<H>` periods ahead." It is a
claim about **past out-of-sample accuracy**. The sentence is written by code
(`contracts.render_forecast_claim`); the gateway refuses any other sentence and the words proven,
prove, true, correct, will be, will, guaranteed, certain (`admissibility.FORECAST_REFUSED_TERMS`).
A PASS is shown as **"held up in backtest"** with the sentence "This measures how accurate the
method was on earlier periods. It does not guarantee the next periods." The forecast numbers
themselves stay in the Measured tier and are labelled Measured.

| Part | Where |
|---|---|
| The test: rolling-origin backtest on the held-back periods; each origin fitted on a read-only copy of the periods before it; block sign-flip (swap) test of the method's loss against the baseline's; effect = 1 - MASE ratio | `verification/stats/forecast.py` |
| Admissibility, plan and NOT_TESTABLE reasons, vetted template, llm refusal | `admissibility.py`, `schemes.py` (`_forecast_plan`), `falsification/templates.py`, `generator.py` |
| Attacks F1-F6 (one-way ratchet, `applicable` reported honestly) | `verification/attacks/forecast.py` |
| Gateway: optional `history` (the earlier rows, used only to fit), power note, block-bootstrap interval, evidence for the card | `gateway.py`, `forecast_claim.py` |
| Planner: closed-menu `forecast_requests: [{column, horizon}]`; code chooses method and baseline on exploration rows and renders the sentence | `analysis/planner/forecast_claim.py` |
| Wording and card | `api/v1.py`, `web/src/components/ProofCards.tsx`, `Verdict.tsx` |

Contracts changed only by optional fields with defaults (`CandidateInsight.forecast`,
`ProofObject.forecast`) and enum members, so every stored proof and candidate still loads
(`test_an_old_stored_proof_without_a_forecast_field_still_loads`).

### The six attacks

| id | question | broken when |
|---|---|---|
| F1 | leave each origin out, and drop the best 10% of origins | the error reduction falls to 0 or below |
| F2 | only the most recent third of the origins | the reduction is 0 or below there (a method that worked long ago) |
| F3 | each horizon on its own (not applicable at H = 1) | the reduction is below 0 at any single horizon |
| F4 | the stated 95% range, built on the earlier half of the origins, checked on the later half | coverage is more than 0.10 away from 95%: the result is worded "accuracy held up, but the stated range is not calibrated" and is NOT a verdict change unless `forecast.attacks.calibration_changes_verdict` is true |
| F5 | CUSUM of the method's one-step errors inside the held-back window (5% point 1.358), then the reduction after the break | a break is found and the reduction after it is 0 or below |
| F6 | drop origins whose loss is an outlier (robust z above `attacks.outlier_z`, at most 10% of origins) for either forecast | the reduction falls to 0 or below |

A broken check is worded "not proof the forecast is bad": it means the backtest's advantage did
not survive that check on these periods.

## 2. How it was measured

`scripts/calibration/forecast_claim_card.py`. For every replicate the **same library code the
gateway runs**, in-process: the planner's exploration-only choice of method and baseline
(`_select`), the gateway's own plan and refusals (`assign_plan`), the backtest and the block
sign-flip test, the band and direction (`evaluate_gate`), and for a claim that passes the six
attacks. A **family of one claim**, so q = p (BH is a no-op there), like the existing gate report
card; BH over several claims is the gateway's and is covered by `test_a_forecast_enters_the_same_bh_family_as_other_claims`.
Section 6 checks the in-process path against the real gateway (sandbox, HMAC stamp).

* **Reduced permutations: 999 per test (production 10,000).** The card only. It coarsens p-values
  (smallest two-sided p is 2/1000) and changes nothing else.
* 200 replicates per cell, monthly series of 36, 60 and 120 months, horizon H = 2 ("the next two
  months"), alpha 0.05, the shipped effect band and attack thresholds, the shipped 50/50 time split
  (the confirmation share is raised to 20 periods on a short series, as `split_rows` does).
* Seed 20261025; each replicate is `default_rng([seed, shape, n, rep])`.
* 95% Wilson intervals in square brackets; a rate over 200 replicates has a standard error up to
  0.035.

Planted shapes (noise sd 2, seasonal amplitude about 10, growth 0.5 per month where stated):

| shape | what it is | truth |
|---|---|---|
| `null_rw` | random walk, no seasonality | nothing can beat a last-value forecast |
| `null_rw_literal` | the same walk with the baseline forced to seasonal-naive (the design as first written) | a smooth method beats a seasonal-naive forecast on a walk, so a PASS is a true sentence that says little (section 3, D1) |
| `null_srw` | seasonal random walk, y[t] = y[t-12] + noise | seasonal-naive is the best possible forecast; nothing beats it |
| `true` | stable seasonal pattern with growth | a trend-and-season method beats the baselines |
| `break` | `true` plus a level shift of +15 halfway through (at the edge of the held-back window) | the history is no longer the future |
| `break_late` | the shift three quarters through (inside the window) | the case F5 looks for |
| `h1only` | the `true` series, scored with a planted forecaster: accurate one period ahead, biased by +7 two ahead (about as far off as seasonal-naive) | good at h = 1, not at h = 2 |

## 3. Where the build differs from the design, and why

Each is a deviation from the brief; each has a reason; each is easy to reverse in config or code.

* **D1. The baseline is chosen on exploration rows: seasonal-naive or last-value, whichever had the
  lower error there (`forecast.baseline: auto`; `seasonal_naive` forces the design as written).
  The sentence names the one chosen.** Reason: on a series with no season a seasonal-naive
  forecast copies last year's noise, so a smooth method beats it. "Beats a seasonal-naive forecast"
  is then a true sentence that says almost nothing (`null_rw_literal` below: 55% PASS on a random
  walk where a last-value forecast is the best there is). The brief's own null, "random walk with
  no seasonality: nothing can beat naive", is only a null against a last-value baseline.
  The choice uses exploration rows only (the planner never sees held-back periods), so it adds no
  test on the held-back ones.
* **D2. The gateway takes `history` (the exploration rows) to fit the method; only the held-back
  periods are scored.** Reason: with only the held-back rows a 60-month series (30 held back) has
  too little history before its first origin. `history` is the exploration split exactly, never a
  held-back row, and only forecast claims read it. Every origin is fitted on a read-only copy of
  the periods before it (`test_each_origin_is_fitted_on_the_past_only`,
  `test_changing_the_future_never_changes_an_earlier_forecast`).
* **D3. Blocks of origins have length H, and a claim needs at least 11 blocks and 12 origins
  (`forecast.min_blocks`, `min_origins`).** Reason: a sign-flip null over k blocks has 2**k
  patterns, so its smallest two-sided p is about 2 / 2**k; the loader refuses a config where
  2**min_blocks cannot resolve `alpha / m_max` (k = 11 at m_max 40). It follows that a claim two
  periods ahead needs 46 months, three ahead 65, six ahead 131 (checked with `assign_plan`);
  one ahead needs 36. Below that the answer is NOT_TESTABLE with the counts in the reason.
* **D4. Two-sided p by doubling the smaller add-one tail; the stamped statistic is the effect
  (`1 - MASE ratio`).** Reason: the executor requires the effect to be the stamped statistic, and
  the repo's templates are two-sided with the direction checked apart (a negative effect is
  REFUTED, not PASS). `asserted_direction` must be positive for a forecast claim, or a method
  significantly worse than the baseline could pass; the screen refuses anything else.
* **D5. Closed menu of two methods (linear trend with seasonal dummies; Holt-Winters
  exponential smoothing), the same names and fits the Measured tier uses.** Code picks one on
  exploration rows; the model never does. A method with no fit on the last 6 exploration origins is
  not a candidate; if none beat the baseline there the request is dropped, not spent on the family.
* **D6. F4 compares a range built on the earlier half of the origins with the later half**, not
  with the same errors, so it can fail. It is wording only unless the owner's config says so.
* **D7. F5 looks for a break inside the held-back window.** A level shift at the very edge of the
  window moves every error alike and cannot be told from a constant offset; `break` below shows
  what that costs. F5 breaks a claim only when the advantage is gone after the break.
* **D8. Monthly and quarterly data only (`forecast.seasonal_length`), and only when the run was
  split by time.** A panel split by entity, or a random split, leaves no period that is both
  unseen and later than the history, so the claim is NOT_TESTABLE with that reason.
* **D9. The llm generator refuses the type (`GeneratorError`, never a template fallback) and the
  planner does not offer it unless the template generator is selected.**
* **D10. A forecast PASS is written to memory like any PASS** (`memory_write => verdict == PASS` is
  unchanged and not touched). The generic lesson text ("verification supported a positive
  forecast involving ...") is not forecast-specific; whether forecasts should be remembered at
  all is the owner's call.

## 4. Results (horizon 2, 200 replicates per cell, 999 permutations)

`planner dropped` = the planner would not have proposed the claim (no method beat its baseline on
the exploration periods, or too few exploration periods to choose). `not testable` = the gateway
refused with a plain reason. `gate pass` = q < alpha, effect in its band, direction right.
`final PASS` = after the attacks. All percentages are of ALL 200 replicates unless said otherwise.

| shape | n | reps | planner dropped | not testable | tested | gate pass | final PASS | FRAGILE | effect q10 / q50 / q90 |
|---|---|---|---|---|---|---|---|---|---|
| null_rw | 60 (H=2) | 200 | 71.5% [65, 77] | 0.0% [0, 2] | 57 | 2.0% [1, 5] | 2.0% [1, 5] | 0.0% [0, 2] | -2.09 / -0.28 / +0.13 |
| null_rw | 120 (H=2) | 200 | 70.5% [64, 76] | 0.0% [0, 2] | 59 | 0.5% [0, 3] | 0.5% [0, 3] | 0.0% [0, 2] | -1.80 / -0.12 / -0.02 |
| null_rw_literal | 60 (H=2) | 200 | 13.0% [9, 18] | 0.0% [0, 2] | 174 | 59.0% [52, 66] | 55.0% [48, 62] | 4.0% [2, 8] | -0.03 / +0.50 / +0.70 |
| null_rw_literal | 120 (H=2) | 200 | 9.5% [6, 14] | 0.0% [0, 2] | 181 | 79.0% [73, 84] | 78.5% [72, 84] | 0.5% [0, 3] | +0.08 / +0.59 / +0.70 |
| null_srw | 60 (H=2) | 200 | 69.5% [63, 75] | 0.0% [0, 2] | 61 | 0.0% [0, 2] | 0.0% [0, 2] | 0.0% [0, 2] | -0.41 / -0.23 / -0.09 |
| null_srw | 120 (H=2) | 200 | 81.0% [75, 86] | 0.0% [0, 2] | 38 | 0.0% [0, 2] | 0.0% [0, 2] | 0.0% [0, 2] | -0.84 / -0.51 / -0.02 |
| true | 60 (H=2) | 200 | 4.0% [2, 8] | 0.0% [0, 2] | 192 | 96.0% [92, 98] | 96.0% [92, 98] | 0.0% [0, 2] | +0.63 / +0.68 / +0.74 |
| true | 120 (H=2) | 200 | 0.5% [0, 3] | 0.0% [0, 2] | 199 | 99.5% [97, 100] | 99.5% [97, 100] | 0.0% [0, 2] | +0.67 / +0.71 / +0.75 |
| break | 60 (H=2) | 200 | 1.0% [0, 4] | 0.0% [0, 2] | 198 | 39.5% [33, 46] | 39.5% [33, 46] | 0.0% [0, 2] | +0.08 / +0.28 / +0.51 |
| break | 120 (H=2) | 200 | 0.0% [0, 2] | 0.0% [0, 2] | 200 | 77.0% [71, 82] | 77.0% [71, 82] | 0.0% [0, 2] | +0.21 / +0.49 / +0.71 |
| break_late | 60 (H=2) | 200 | 0.5% [0, 3] | 0.0% [0, 2] | 199 | 44.5% [38, 51] | 44.5% [38, 51] | 0.0% [0, 2] | +0.06 / +0.22 / +0.53 |
| break_late | 120 (H=2) | 200 | 0.0% [0, 2] | 0.0% [0, 2] | 200 | 74.0% [68, 80] | 74.0% [68, 80] | 0.0% [0, 2] | +0.09 / +0.47 / +0.71 |
| h1only | 60 (H=2) | 200 | 0.0% [0, 2] | 0.0% [0, 2] | 200 | 61.0% [54, 67] | 8.5% [5, 13] | 52.5% [46, 59] | +0.15 / +0.26 / +0.36 |
| h1only | 120 (H=2) | 200 | 0.0% [0, 2] | 0.0% [0, 2] | 200 | 98.5% [96, 99] | 3.0% [1, 6] | 95.5% [92, 98] | +0.22 / +0.28 / +0.33 |
| null_rw | 36 (H=2) | 200 | 100.0% [98, 100] | 0.0% [0, 2] | 0 | 0.0% [0, 2] | 0.0% [0, 2] | 0.0% [0, 2] | n/a |
| null_rw_literal | 36 (H=2) | 200 | 100.0% [98, 100] | 0.0% [0, 2] | 0 | 0.0% [0, 2] | 0.0% [0, 2] | 0.0% [0, 2] | n/a |
| null_srw | 36 (H=2) | 200 | 100.0% [98, 100] | 0.0% [0, 2] | 0 | 0.0% [0, 2] | 0.0% [0, 2] | 0.0% [0, 2] | n/a |
| true | 36 (H=2) | 200 | 100.0% [98, 100] | 0.0% [0, 2] | 0 | 0.0% [0, 2] | 0.0% [0, 2] | 0.0% [0, 2] | n/a |
| break | 36 (H=2) | 200 | 100.0% [98, 100] | 0.0% [0, 2] | 0 | 0.0% [0, 2] | 0.0% [0, 2] | 0.0% [0, 2] | n/a |
| break_late | 36 (H=2) | 200 | 100.0% [98, 100] | 0.0% [0, 2] | 0 | 0.0% [0, 2] | 0.0% [0, 2] | 0.0% [0, 2] | n/a |
| h1only | 36 (H=2) | 200 | 0.0% [0, 2] | 100.0% [98, 100] | 0 | 0.0% [0, 2] | 0.0% [0, 2] | 0.0% [0, 2] | n/a |

| shape | n | gate pass | F1 | F2 | F3 | F4 | F5 | F6 | range not calibrated |
|---|---|---|---|---|---|---|---|---|---|
| null_rw | 60 (H=2) | 4 | 0 / 4 / 0 | 0 / 4 / 0 | 0 / 4 / 0 | 0 / 4 / 0 | 0 / 4 / 0 | 0 / 4 / 0 | 0 |
| null_rw | 120 (H=2) | 1 | 0 / 1 / 0 | 0 / 1 / 0 | 0 / 1 / 0 | 0 / 1 / 0 | 0 / 1 / 0 | 0 / 1 / 0 | 1 |
| null_rw_literal | 60 (H=2) | 118 | 0 / 118 / 0 | 8 / 118 / 0 | 0 / 118 / 0 | 0 / 118 / 0 | 2 / 118 / 0 | 0 / 118 / 0 | 40 |
| null_rw_literal | 120 (H=2) | 158 | 0 / 158 / 0 | 1 / 158 / 0 | 0 / 158 / 0 | 0 / 158 / 0 | 0 / 158 / 0 | 0 / 158 / 0 | 40 |
| null_srw | 60 (H=2) | 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| null_srw | 120 (H=2) | 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| true | 60 (H=2) | 192 | 0 / 192 / 0 | 0 / 192 / 0 | 0 / 192 / 0 | 0 / 192 / 0 | 0 / 192 / 0 | 0 / 192 / 0 | 57 |
| true | 120 (H=2) | 199 | 0 / 199 / 0 | 0 / 199 / 0 | 0 / 199 / 0 | 0 / 199 / 0 | 0 / 199 / 0 | 0 / 199 / 0 | 23 |
| break | 60 (H=2) | 79 | 0 / 79 / 0 | 0 / 79 / 0 | 0 / 79 / 0 | 0 / 79 / 0 | 0 / 78 / 1 | 0 / 79 / 0 | 9 |
| break | 120 (H=2) | 154 | 0 / 154 / 0 | 0 / 154 / 0 | 0 / 154 / 0 | 0 / 154 / 0 | 0 / 152 / 2 | 0 / 154 / 0 | 63 |
| break_late | 60 (H=2) | 89 | 0 / 89 / 0 | 0 / 89 / 0 | 0 / 89 / 0 | 0 / 89 / 0 | 0 / 89 / 0 | 0 / 89 / 0 | 88 |
| break_late | 120 (H=2) | 148 | 0 / 148 / 0 | 0 / 148 / 0 | 0 / 148 / 0 | 0 / 148 / 0 | 0 / 148 / 0 | 0 / 148 / 0 | 115 |
| h1only | 60 (H=2) | 122 | 0 / 122 / 0 | 2 / 122 / 0 | 105 / 122 / 0 | 0 / 122 / 0 | 0 / 122 / 0 | 0 / 122 / 0 | 19 |
| h1only | 120 (H=2) | 197 | 0 / 197 / 0 | 2 / 197 / 0 | 191 / 197 / 0 | 0 / 197 / 0 | 0 / 197 / 0 | 0 / 197 / 0 | 12 |
| null_rw | 36 (H=2) | 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| null_rw_literal | 36 (H=2) | 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| null_srw | 36 (H=2) | 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| true | 36 (H=2) | 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| break | 36 (H=2) | 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| break_late | 36 (H=2) | 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| h1only | 36 (H=2) | 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |

"range not calibrated" counts claims whose F4 wording fired (accuracy held up, stated range not
calibrated); it is not a broken check and does not change the verdict.

## 5. Reading the numbers

**False PASS under a null (the sizes: at or below alpha = 0.05).**

* `null_rw` (random walk, nothing beats a last-value forecast): final PASS **2.0% [1, 5]** at 60
  months and **0.5% [0, 3]** at 120. Most requests never reach the gate (70% are dropped because no
  method beat its baseline on the exploration periods). Among the ones that were tested, 4 of 57
  (7.0% [3, 17]) and 1 of 59 (1.7% [0, 9]) passed: 4 events, compatible with 5%.
* `null_srw` (seasonal-naive is the best possible forecast): **0 of 200** at 60 and at 120
  (0.0% [0, 2]).
* `null_rw_literal` (the design as first written, baseline forced to seasonal-naive):
  **55.0% [48, 62] at 60 months and 78.5% [72, 84] at 120.** These are not false alarms about a
  true null: a smooth method does beat a seasonal-naive forecast on a random walk, so the sentence
  is true. They show that "beats a seasonal-naive forecast" is no evidence of skill on a series with
  no season, which is why D1 chooses the baseline on exploration rows.
* In the null cells the method is often significantly WORSE than the baseline (`refuted` in
  `gate_outcomes`: 29 of 57 tested at 60 months, 28 of 59 at 120 on `null_rw`); two-sided testing
  with a positive asserted direction sends those to REFUTED, never PASS.
* At 36 months and two periods ahead nothing reaches the gate: the planner drops every request
  (100% [98, 100]) because 16 exploration periods are too few to choose a baseline. With the planner
  bypassed (`--force-default`, `card_h2_36_forced_default.json`) the gateway itself answers
  NOT_TESTABLE for 200 of 200: 11 origins, 6 blocks, and a sign-flip null over 6 blocks cannot reach
  alpha.

**Power on the true series.** `true`: final PASS **96.0% [92, 98]** at 60 months and **99.5% [97,
100]** at 120 (192 of 192 and 199 of 199 of the claims that reached the gate; the other 4% and 0.5%
were dropped by the planner because no method beat its baseline on the exploration periods). At 36
months: 0% (the planner drops the request; the gateway would say NOT_TESTABLE).

**False kill of the attacks on the true series: 0 of 192 and 0 of 199 (0.0% [0, 2]).** No attack
broke a true claim at either length. The cost is on the wording: the F4 note "range not calibrated"
fired on 57 of 192 true claims (29.7% [24, 36]) at 60 months and 23 of 199 (11.6% [8, 17]) at 120.
A 95% range built on the 28 errors of the earlier origins is estimated from nearly its extremes, so
its coverage on the later origins often falls below 85% by chance; the tolerance (0.10) is the
owner's to change, and F4 changes no verdict.

**Structural break.**

* `break` (shift at the edge of the held-back window): **39.5% [33, 46] still PASS at 60 months and
  77.0% [71, 82] at 120.** F5 broke 0 of 79 and 0 of 154. The method, fitted before the shift,
  adapts afterwards and beats a last-value baseline over the held-back months, so "held up in
  backtest" is a true statement about them; it is not a statement that the series is stable.
  F4's range note fired on 9 of 79 (11%) and 63 of 154 (41%).
* `break_late` (shift inside the window): 44.5% [38, 51] and 74.0% [68, 80] PASS; **F5 broke 0 of 89
  and 0 of 148.** F4's note fired on 88 of 89 (99%) and 115 of 148 (78%): at H = 2 it is F4, as
  wording, that sees the break, and no verdict changes.
* F5 does act when a break leaves the advantage gone: in the diagnostic of section 7 (36 months, one
  period ahead, shift inside the window) it broke 39 of 195 passing claims and F2 45 of 195; the final
  PASS rate fell to 69.0% [62, 75] with 28.5% [23, 35] FRAGILE.
* So **the gate does not detect a break unless the method's advantage is gone after it**, and a
  break between the fitting window and the test window is not detected by F5 at all (D7). The
  honest label is the one the claim carries: past accuracy on the held-back months.

**Horizon-2 failure** (`h1only`: accurate one period ahead, biased two ahead). The gate passed it
61.0% [54, 67] (60 months) and 98.5% [96, 99] (120) before the attacks: overall it is better than the
baseline. **F3 broke 105 of 122 (86.1%) and 191 of 197 (97.0%) of those**, so final PASS fell to
**8.5% [5, 13] and 3.0% [1, 6]**. The 17 and 6 that survived are series where the h = 2 reduction was
not negative in that sample. F2 broke 2 and 2.

**The effect band.** Across the 1,142 replicates (every shape except the planted `h1only`) where
the test was significant with the right sign, the smallest effect was 0.164 (error reduction), the
1st percentile 0.289 and none was below 0.10; the five that passed under a null had effects 0.19 to
0.75. So the floor of 0.10 (`evidence.effect_thresholds.mase_reduction.min`; `strong` 0.40) bound
on none of them and cannot separate a lucky pass from a real one; q < alpha does that. It sits at
about 60% of the smallest effect seen and is PROVISIONAL, like the other convention-based bands.

## 6. The in-process card against the real gateway

`python scripts/calibration/forecast_claim_card.py --crosscheck 8`: the same series run through the
real gateway (`verify_batch_with_summary`: sandboxed subprocess, HMAC stamp, plan, BH, band, then
attacks) and through the card's in-process path. 17 series were compared (7 more were dropped by the
planner on both paths): **p-value, effect and final outcome identical in 17 of 17**
(`docs/evidence/forecast_claim_2026-10-25/crosscheck.json`). The card's rates are therefore rates of
the gateway's own code, apart from the reduced permutation count.

## 7. A diagnostic: 36 months, one period ahead, planner bypassed

At one period ahead a 36-month series is testable (12 origins, 12 blocks). The exploration half is
then too short (16 periods) for the planner to choose a baseline, so the planner now refuses the
request (all four shapes: 100% dropped; `card_h1.json`). Forcing the default method and the
seasonal-naive baseline through anyway (`--force-default`, `card_h1_forced_default.json`) shows why
it refuses:

| shape | n | reps | planner dropped | not testable | tested | gate pass | final PASS | FRAGILE | effect q10 / q50 / q90 |
|---|---|---|---|---|---|---|---|---|---|
| null_rw | 36 (H=1) | 200 | 0.0% [0, 2] | 0.0% [0, 2] | 200 | 32.5% [26, 39] | 30.0% [24, 37] | 2.5% [1, 6] | -0.36 / +0.18 / +0.57 |
| null_srw | 36 (H=1) | 200 | 0.0% [0, 2] | 0.0% [0, 2] | 200 | 0.0% [0, 2] | 0.0% [0, 2] | 0.0% [0, 2] | -0.41 / -0.12 / +0.08 |
| true | 36 (H=1) | 200 | 0.0% [0, 2] | 0.0% [0, 2] | 200 | 94.5% [90, 97] | 94.5% [90, 97] | 0.0% [0, 2] | +0.55 / +0.66 / +0.76 |
| break | 36 (H=1) | 200 | 0.0% [0, 2] | 0.0% [0, 2] | 200 | 97.5% [94, 99] | 69.0% [62, 75] | 28.5% [23, 35] | +0.64 / +0.71 / +0.76 |

| shape | n | gate pass | F1 | F2 | F3 | F4 | F5 | F6 | range not calibrated |
|---|---|---|---|---|---|---|---|---|---|
| null_rw | 36 (H=1) | 65 | 0 / 65 / 0 | 5 / 65 / 0 | 0 / 0 / 65 | 0 / 65 / 0 | 0 / 65 / 0 | 0 / 65 / 0 | 55 |
| null_srw | 36 (H=1) | 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 |
| true | 36 (H=1) | 189 | 0 / 189 / 0 | 0 / 189 / 0 | 0 / 0 / 189 | 0 / 189 / 0 | 0 / 189 / 0 | 0 / 189 / 0 | 156 |
| break | 36 (H=1) | 195 | 0 / 195 / 0 | 45 / 195 / 0 | 0 / 0 / 195 | 0 / 195 / 0 | 39 / 195 / 0 | 0 / 195 / 0 | 195 |

On a random walk the default baseline gives a **30.0% [24, 37] false PASS**, the `null_rw_literal`
problem again. (The `h1only` shape is not meaningful at one period ahead and is left out.)

## 8. What the numbers say about the default (the owner decides)

`claims.forecast_enabled` stays **false** in this PR. What the measurements support and what they
do not:

* They support that, **with the baseline chosen on exploration rows**, the test's false-PASS rate on
  a random walk and on a seasonal random walk was at or below alpha in every cell (at most 2.0%),
  its power on a stable seasonal series with growth was 96% to 99.5% from 60 months, and the
  attacks did not break a true claim in 391 tries.
* They do not support a default of "on" with the baseline as the brief first described it
  (seasonal-naive always): 55% to 78% of random-walk series pass.
* They show three things the owner may want changed before it is on: (1) F5 never fires at the
  boundary or later at two periods ahead, so a structural break does not stop a claim whose method
  still beats its baseline afterwards (F4's wording is the only signal); (2) F4's "range not
  calibrated" note fires on 12% to 30% of true claims at these lengths; (3) at two periods ahead
  the claim needs 46 months, at three 65, at six 131, so on a typical 24 to 36 month finance
  table it is not proposed (or, if asked for directly, NOT_TESTABLE with the reason).
* They say nothing about real tables, other noise levels, other horizons, other methods, or the
  BH family with other claims in it.

If it is switched on for a review, I would only do so for monthly tables of at least 46 months,
horizon 2 or less, with `forecast.baseline: auto`, and with the planner offering one request per
run at most; none of this is a measured result, it is a reading of the tables above.

## 9. Limits (read these before quoting a number)

* **Synthetic, author-built, and the same author built the claim.** The shapes are plausible, not
  representative. Real revenue series have trend breaks, promotions, holidays that move, partial
  months and outliers that none of these shapes has.
* **A family of one claim per replicate.** BH over several claims is the gateway's and is tested
  structurally, not measured here; the correlated-family calibration of the earlier note was not
  repeated with forecast claims in the family.
* **Reduced permutations (999) in the card.** Production uses 10,000; the p-values are finer there.
* **One noise level, one seasonal amplitude, one break size (+15, about 7 noise sds),
  horizon 2.** Other horizons have different testability (D3) and were not measured.
* **Dependence in the loss differential is handled by blocks of length H.** A method that is
  persistently misspecified (an OLS line on a random walk) has errors that stay one-sided for far
  more than H origins; there the null is anti-conservative. The random-walk cells measure it for the
  two methods in the menu; nothing is known for other series.
* **F4 and F5 are heuristics** (a range built on half the origins; a CUSUM with the 5% Kolmogorov
  point on possibly autocorrelated errors). Their false-kill and detection rates are in section 5
  and are measured on the planted shapes only.
* **A backtest is not a forecast.** A held-up claim says the method was closer than the baseline on
  held-back periods. A new product, a price change or a calendar shift after the table ends defeats
  it, and F5 cannot see a break at the edge of the window or after it.
* **Holt-Winters is slow** (about 0.2 s per fit). A 120-month series takes roughly 12 s inside the
  60 s sandbox limit; a series several times longer could time out, which fails closed
  (INCONCLUSIVE, "exceeded the timeout"); it was not measured.
* **Not tested here:** real tables, the live planner call, the web card in a browser at 390 px and
  1366 px (the type check and build pass; no screenshots were taken), Docker.

## 10. Reproduce

From the repo root (Python 3.13, `pip install -e .` and `pip install -r requirements/verification.txt
-r requirements/dev.txt -r requirements/runtime.txt -r requirements/analysis.txt`), 4 cores:

```
python scripts/calibration/forecast_claim_card.py --reps 200 --workers 4 --horizon 2 \
    --out docs/evidence/forecast_claim_2026-10-25/card_h2.json      # seed 20261025, about 2.5 h
python scripts/calibration/forecast_claim_card.py --reps 200 --workers 4 --horizon 1 \
    --shapes null_rw null_srw true --lengths 36 \
    --out docs/evidence/forecast_claim_2026-10-25/card_h1.json
python scripts/calibration/forecast_claim_card.py --crosscheck 10
python -m pytest tests/unit/verification/test_forecast_stats.py \
    tests/unit/verification/test_forecast_claim.py tests/unit/analysis/test_planner_forecast.py
```

The raw per-replicate records are in `docs/evidence/forecast_claim_2026-10-25/`.
