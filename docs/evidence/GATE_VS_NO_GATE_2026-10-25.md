# E1: the gate versus no gate on planted-truth tables (2026-10-25)

Status: DESIGN, written before the first full run. Results are appended in a later commit below the line "RESULTS". Nothing in the design section is edited after the run.

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

Config: `configs/verification.yaml` as shipped, with two changes, both visible in `experiment_config()`: `llm.generator = template`, `statistics.n_permutations` reduced to the value printed in the results header (shipped value 10,000). Alpha 0.05, effect bands, attack settings, 50/50 split, `m_max` 40 are unchanged. The gateway seed for table k is `20261025 + k`.

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
