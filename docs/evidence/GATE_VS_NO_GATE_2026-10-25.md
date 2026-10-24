# E1: the gate versus no gate on planted-truth tables (2026-10-25)

Status: design (sections 1-6) written and committed before the first full run; results are in the RESULTS section at the end. Nothing in the design section is edited after the run.

Experiment E1 of `docs/RESEARCH_improvements.md` (branch `docs/satya/research-improvements`). Script: `scripts/calibration/eval_gate_ablation.py`.

## 1. Question

For the same 12 candidate claims on the same table, how many false reports does each decision rule make, and what does the full gate cost in true findings kept?

## 2. Data (synthetic, author-built, one planted family)

K = 200 tables, generated from seed `20261025` (table k uses `numpy.random.default_rng([20261025, k])`). Each table has 12 candidate claims, enumerated by code. The planner and every model are out of the loop.

Each table is one cell of a balanced 27-cell cycle (cell = k mod 27 pattern, so every cell appears 7 or 8 times in 200 tables):

| factor | levels | rule |
|---|---|---|
| structure | independent rows; shared season; entity clusters | `k mod 3` |
| rho of every true claim in the table | 0.15, 0.3, 0.5 | `(k div 3) mod 3` |
| number of true claims of 12 | 2, 4, 6 | `(k div 9) mod 3` |

Which claims are true is a seeded random subset. Truth is known exactly, so every count is a count, not an estimate.

* **Independent rows:** 200 rows, 12 pairs (x_j, y_j), y = rho x + sqrt(1 - rho^2) noise for true pairs, independent noise for null pairs.
* **Shared season:** 36 months x 6 rows (216 rows). Within each pair both columns carry the same sinusoidal season (amplitude 3, random phase per pair), so the raw correlation is large for EVERY pair, true or null. A true pair also has a within-month link of strength rho. Declared as `transactions` by month. A row-level test cannot tell the pairs apart; only a test inside months can.
* **Entity clusters:** 40 entities x 6 months (240 rows). 12 claims "y differs between label b and label a", the label fixed per entity. Entity level = rho x (label as +1/-1) + sqrt(1 - rho^2) x entity noise; row noise sd 0.5. Declared as a `panel`. For null claims the entity effect is still large, so a row-level test is far too eager.

All claims assert a positive direction (for the cluster claims: label b higher than label a, `reference_group = "b"`).

## 3. Arms

| arm | reports a claim when | rows used |
|---|---|---|
| A naive | uncorrected two-sided p < 0.05 and the asserted sign (Spearman for pairs, Mann-Whitney for groups) | all rows |
| B BH only | the real gateway's raw p, BH q < 0.05 across the 12 claims, observed direction positive; no effect floor, no attacks | confirmation half (the gate's own split) |
| B+ BH and floor | B plus the effect-size floor (gate outcome SUPPORTED or FRAGILE, i.e. the verdict before attacks) | confirmation half |
| C full gate | the real gateway verdict is PASS (split, scheme-matched null, BH, effect band, attacks) | confirmation half |

B, B+ and C are read from ONE `verify_batch` call per table (the real gateway, template generator, real sandbox), so they differ only in which stage's output is used. B+ is an extra rung of the ladder that the free design allows; the requested arms are A, B and C. Arm A is computed by the script and does not use the gateway. The spec names arm B "BH only on the confirmation half"; it uses the gateway's p-values, which come from the scheme-matched null (stratified for the season table, cluster for the entity table), not a naive test. So B already contains the "right null". It is a stricter baseline than a typical user's BH.

Config: `configs/verification.yaml` as shipped, with two changes, both visible in `experiment_config()`: `llm.generator = template`, `statistics.n_permutations` reduced to 1,000 (shipped value 10,000; the smallest p-value is then 1/1001, below the BH cut-off for 12 claims, and the config loader's resolution rule for `m_max` 40 still holds). Alpha 0.05, effect bands, attack settings, 50/50 split, `m_max` 40 are unchanged. The gateway seed for table k is `20261025 + k`.

**Executor deviation (labelled).** The real gateway runs every test in a subprocess sandbox. On this machine, interpreter start-up with numpy, pandas and scipy costs 30 to 40 seconds per claim (measured: one claim took 50 s through the sandbox), so 2,400 claims would take days. The script therefore replaces only `executor.runner._run_once` with an in-process version that execs the same vetted template source, round-trips the payload through JSON, and passes it through the real `_validate_payload` (provenance stamp, scheme, resample count, seed). The import and column policies, the split, scheme assignment, BH, the effect band, intervals and attacks are the real gateway code. What is skipped is process isolation and the time and memory limits, which are irrelevant for the repository's own template. Equality of the in-process and sandbox p-values on sample claims is checked and reported in the results. `--sandbox` restores the subprocess.

## 4. Metrics (fixed now)

Per table and arm: number reported R; false reports V (reported claim that is not truly related); true kept T; recall = T / (true claims in the table); false discovery proportion FDP = V / R (0 when R = 0).

Per arm, over the 200 tables: mean of each, with the Monte-Carlo standard error (sd across tables / sqrt(200)) and a normal 95% interval; share of tables with at least one false report with a Wilson 95% interval; pooled V / R across tables. Breakdowns by rho and by structure. Cost: wall seconds per table (B, B+ and C share one gateway call, so their cost is the same number and cannot be split).

Headline numbers: mean false reports per table, mean FDP (the empirical FDR), mean recall.

## 5. What a bad result looks like (committed in advance)

1. Arm C (or B) has mean FDP above 0.05 by more than its 95% interval (that is, lower end of the interval above 0.05), or reports a false finding on more than about 10% of tables that have only a few true claims. Then the gate leaks; report it, do not touch alpha, and escalate to the verification owner (E2 and the correlated-claims question come next).
2. Arm A is not clearly worse than arm C (false reports per table within a factor of about 2, or the gap inside the intervals). Then the tables are too easy and the experiment shows nothing about the gate.
3. Arm C keeps under half of the true claims at rho 0.5, or under about 0.2 overall. That is the price of the 50/50 split, the floor and the attacks together; it is reported as the cost, and no threshold is changed to hide it. At rho 0.15 low recall is expected, because the confirmation half has about 100 rows (power for rho 0.15 at n = 100 is about 0.3 before any correction).
4. Gateway errors or NOT_TESTABLE claims in more than about 5% of claims. Then the arms are not comparing like with like; the count is reported and the tables are not dropped.

No rerun after seeing the numbers. If a bug in the script is found, the fix, the reason and both outputs are recorded here.

## 6. Reproduction (full run)

```
cd C:\Users\pasar\Desktop\pramana-v2
set PYTHONPATH=src
C:\Users\pasar\Desktop\pramana\.venv\Scripts\python.exe scripts/calibration/eval_gate_ablation.py --tables 200 --permutations 1000 --workers 8 --out artifacts/e1_gate_ablation.json
```

Fast plumbing test: `pytest tests/unit/verification/test_eval_gate_ablation.py`.

---

# RESULTS

Run on 2026-10-25, once. Command in section 6. 200 tables, 2,400 claims, 782 truly related claims (pooled), 1,000 permutations, in-process executor, 8 worker processes, wall time 1,102 s (18 minutes) on a machine shared with about 14 other busy Python processes. Raw output: `artifacts/e1_gate_ablation.json` (git-ignored; regenerate with the command). Gateway errors: 0. NOT_TESTABLE claims: 0 of 2,400. Every claim entered the BH family (12 per table).

Notation: mean over the 200 tables, (Monte-Carlo SE across tables), [normal 95% interval]. FDP is V/R per table, 0 when nothing is reported, so its mean is the empirical FDR, E[V/R] with V/R = 0 when R = 0.

## Headline

| arm | reported / table | false reports / table | recall (true claims kept) | FDP (empirical FDR) | tables with at least one false report (Wilson 95%) |
|---|---|---|---|---|---|
| A naive, p < 0.05, all rows | 6.73 (0.29) [6.16, 7.29] | 3.31 (0.26) [2.80, 3.81] | 0.867 (0.018) [0.831, 0.903] | 0.364 (0.022) [0.320, 0.408] | 134/200 = 0.670 [0.602, 0.731] |
| B BH only, confirmation half | 1.92 (0.15) [1.62, 2.21] | 0.085 (0.022) [0.042, 0.128] | 0.465 (0.031) [0.405, 0.525] | 0.022 (0.007) [0.008, 0.035] | 15/200 = 0.075 [0.046, 0.120] |
| B+ BH and effect floor | 1.92 (0.15) | 0.085 (0.022) | 0.465 (0.031) | 0.022 (0.007) | 15/200 = 0.075 |
| C full gate (PASS) | 1.86 (0.15) [1.57, 2.15] | 0.080 (0.022) [0.037, 0.123] | 0.455 (0.030) [0.396, 0.514] | 0.021 (0.007) [0.008, 0.034] | 14/200 = 0.070 [0.042, 0.114] |

Pooled over all tables (counts): A reported 1,345 claims, 661 false (49%), kept 684 of 782 true. B reported 383, 17 false (4.4%), kept 366. C reported 372, 16 false (4.3%), kept 356 of 782 (45.5%). Tables where C reported nothing: 76 of 200.

Cost: arm A takes 0.06 s per table. B, B+ and C share one gateway call and cannot be separated: 39.8 s per table per worker on the shared machine (about 15 s in a quiet single-process probe). The shipped config with 10,000 permutations would make the permutation part about ten times longer.

Reading: the naive rule makes 3.3 false reports per table and 36% of what it reports is false; the gate makes 0.08 false reports per table (about one table in 14 has any) and keeps 45% of the true claims.

## Where the gate loses true findings (recall of C)

By effect size (rho of the true claims):

| rho | tables | A recall | C recall | A false / table | C false / table | C FDP |
|---|---|---|---|---|---|---|
| 0.15 | 68 | 0.651 | 0.069 | 3.28 | 0.03 | 0.020 |
| 0.30 | 66 | 0.963 | 0.548 | 3.36 | 0.11 | 0.019 |
| 0.50 | 66 | 0.994 | 0.760 | 3.27 | 0.11 | 0.024 |

By structure:

| structure | tables | A reported | A false / table | A FDP | C reported | C false / table | C recall | C FDP |
|---|---|---|---|---|---|---|---|---|
| independent rows (200 rows) | 67 | 3.37 | 0.18 | 0.068 | 2.28 | 0.04 | 0.577 | 0.011 |
| shared season (216 rows) | 67 | 12.00 | 8.09 | 0.674 | 2.73 | 0.16 | 0.638 | 0.029 |
| entity clusters (40 entities) | 66 | 4.77 | 1.62 | 0.348 | 0.55 | 0.03 | 0.145 | 0.023 |

C recall by structure and rho (true kept / true claims): independent 8/90, 59/86, 83/86 at rho 0.15, 0.3, 0.5; season 12/90, 74/86, 86/86; entity 1/86, 8/86, 25/86.

By number of true claims out of 12 (2, 4, 6): C false reports per table 0.042, 0.046, 0.159; C pooled false share 0.045, 0.024, 0.056.

## Which stage does the work

* **BH on the confirmation half (arm B) does almost all of it.** Going from A to B removes 3.2 of 3.3 false reports per table. The null that matches the rows (stratified for the season table, cluster for the entity table) is part of B, not an extra.
* **The effect floor (B to B+) removed nothing** in these tables: same 383 reports. The design was built for the BH question and does not test the floor.
* **The attacks (B+ to C) removed 11 reports (FRAGILE), of which 10 were true and 1 was false.** Net effect on false reports: 17 to 16 in 200 tables, a difference that is not distinguishable from noise, at a cost of 10 of 366 true findings (2.7%). The attacks were calibrated on a true moderate effect (design doc); this run does not show them catching null claims that BH let through. This is the least flattering line for the attack set and it is reported as found.

## Against the pre-registered "bad result" lines (section 5)

1. Mean FDP of C is 0.021 with upper 95% limit 0.034, below 0.05; 7.0% of tables had a false report (upper limit 11.4%). Not triggered. BH at 0.05 with 6 to 10 null claims out of 12 is expected to give an FDR of about alpha times the null share (0.025 to 0.042), so 0.021 is consistent with a working procedure.
2. Arm A is much worse than C (3.31 against 0.08 false per table). Not triggered; the tables are not too easy.
3. C keeps 0.76 of the true claims at rho 0.5 and 0.455 overall. Not triggered by the stated thresholds, but the cost is large and uneven: 0.069 at rho 0.15, and 0.145 on entity-cluster tables (0.29 even at rho 0.5), where the confirmation half has only 20 entities. This is the price of a 50/50 split and an honest cluster null on small samples. It is reported, not tuned.
4. No gateway errors, no NOT_TESTABLE claims. Not triggered.

Not pre-registered but worth saying: at rho 0.15 arm C reports 0.34 claims per table with recall 0.069; at that effect size and sample the gate mostly returns "nothing found", which is a statement about the evidence, not about the absence of an effect.

## Executor check

Section 3 describes the in-process executor. The p-value and effect size from it were compared with those from the real subprocess sandbox on sample claims (a throwaway parity script, not committed). Result: for 6 claims (one true and one null on each of the independent-rows, season and entity tables, timeout raised to 400 s so a loaded machine could not fail the sandbox) the p-value and effect size were IDENTICAL to every digit in all 6. In an earlier attempt with the shipped 60 s timeout, one sandbox execution failed under machine load and returned the fail-closed p = 1.0; the in-process run does not have that failure mode, which is another reason it was used. 6 claims is a spot check, not a proof of equivalence.

## Limits (honest)

* **Synthetic and author-built.** One planted family (monotone association on normal data with sinusoidal season and Gaussian entity effects), written by the same person who built the gate. A gate looks good on its author's generators. It says nothing about heavy tails, missing data, skewed or discrete columns, or non-monotone relations.
* **One rule for truth.** A claim is true only if it is a planted pair with the planted sign. Null columns have no dependence by construction; real tables do.
* **Direction is asserted by code on every arm** (positive), so the gate's direction check is not exercised against claims proposed from data.
* **Claims are enumerated by code and fixed by construction, not proposed by a planner from the exploration half.** The 50/50 split protects against selecting claims on the same rows that test them; this experiment never uses the exploration half, so it measures only the cost of testing on half the rows, not what the split buys against a proposer that looks first.
* **Arm A is a naive baseline of my own choosing** (row-level Spearman or Mann-Whitney at 0.05, no correction, all rows). Other naive tools would differ. On independent-row tables it is only mildly bad (FDP 0.068); the large gap comes from the season and cluster tables, where row-level tests are known to be invalid.
* **Arm B already uses the gateway's scheme-matched null**, so it is stricter than a typical user's BH. The gap from A to B mixes a "right null" effect, a multiple-testing effect and a half-the-rows effect; this run does not separate them.
* **Approximations:** 1,000 permutations instead of the shipped 10,000 (coarser p-values, smallest 0.001); in-process execution instead of the subprocess sandbox; one gateway seed per table (20261025 + k); a cycled 27-cell design, not randomised (about 7 tables per cell); Monte-Carlo SE across tables. With 200 tables, FDP 0.021 has a 95% interval of [0.008, 0.034]: evidence against gross leakage, not a certificate of exact control. Claims within a table are independent by construction (separate columns), so dependence between claims is not stressed (that is E2).
* **Cost** was measured on a loaded machine and is a rough upper bound.
* No number here has been signed off by the verification owner (AGENTS.md 8.10).

## What this lets the author say at a thesis review, and what it does not

On synthetic tables built to contain a known set of real and fake relationships, the gate as implemented reported about 0.08 false findings per table of twelve claims, where a plain "p below 0.05 on all the rows" rule reported about 3.3; the share of reports that were false fell from about 36% to about 2%, and 134 of 200 tables carried at least one false report under the naive rule against 14 under the gate. The price was recall: the gate kept 45% of the real relationships, and most of what it missed was weak (rho 0.15), small-sample cluster effects, or both. The correction on the held-back half, not the effect floor and not the attacks, accounts for nearly all of the improvement; in this test the attacks removed ten real findings and one false one. What the author cannot say is that the gate "finds the truth" or "is accurate": every table, every effect shape and the definition of truth were chosen by the author, the claims were handed to the gate rather than proposed from data, the 0.021 error rate has a margin of about 0.013 either side, correlated claims were not tested, and a PASS still means "held up on these rows", never "proven". A defensible sentence is: "On 200 author-built planted tables the gate's false-discovery proportion was 0.02 (95% interval 0.01 to 0.03) against 0.36 for an uncorrected test, at a recall of 0.46."
