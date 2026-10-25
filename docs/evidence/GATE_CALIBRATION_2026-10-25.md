# Gate calibration, 2026-10-25: false PASS in correlated families, false kill and false survive of the attacks

Status: measurement note for the verification owner (P.P. Satya Karthikeya). Nothing in this
note is signed by the owner. Written 2026-10-25 under the overnight delegation (change gateway
behaviour only behind a flag that defaults to today's behaviour, unless the measurements justify
a new default). **No verdict-changing default was changed.** Section 6 says what changed and what
was refused.

All data are **synthetic and author-built**: tables I planted with known truth, run through the
repo's own code. They show how the gate and the attacks behave on those shapes. They do not show
how often the gate is right on a real table, and they were not tuned on anything real.

## 1. What was measured

| Part | What runs | Replicates |
|---|---|---|
| Correlated family (section 3) | The **real gateway** (`verify_batch`, vetted template tests, sandbox, one BH correction over 8 claims that share columns, effect floor, direction, then attacks A1-A7), `m_max = 8`, alpha 0.05 | 200 per design, 6 designs |
| False kill and false survive (section 4) | The real attack code (`run_attacks`) on tables that cleared a **stand-in gate** (Spearman p < 0.05 and |rho| >= 0.10, a family of one claim), A2 under both rules on the very same tables | 200 gate-clearing tables per cell, 54 cells |
| Planted flaw (section 5) | Same as above, on tables where the link exists only in the last third of the months | 200 per cell, 3 cells |
| Stand-in check (section 7) | Real gateway against the stand-in on one cell | 300 |

Definitions. **False kill**: a true effect passes the test and an attack then breaks it (the
claim becomes FRAGILE, a REJECT, and is never stored). **False survive**: a claim with no effect
that passed the test by luck is *not* broken. **Luck-pass** = a null table that cleared the gate.
"n" is the number of rows the gateway and the attacks are handed. `verify_batch` does not split
rows itself; the product hands it the **confirmation half** of an upload, so a 240-row upload is
n = 120 here. Planted effects are Spearman rho 0.2 and 0.3 (bivariate
normal with Pearson r = 2 sin(pi rho / 6)).

Shapes (author-built): `gaussian`; `heavy_tail` (t with 3 degrees of freedom noise); `skewed`
(y lognormal); `outliers` (5% of rows replaced by independent draws at 8 sd); `many_columns` (the
table also carries 9 columns that are noisy copies of x, so A3 has many controls to search);
`series` (one row per month, the link is in the monthly changes; block-differenced null).
Every non-series table also has a column tied to x and a three-level grouping column, so A3 and A4
have something to examine.

Test configuration (labelled, never used for production): template generator; `m_max` 8;
families use 1000 permutations (production 10000) and 200 interval resamples (production 1000,
descriptive only); attack grids use 300 resamples for the A2 interval rule (production 1000).
Alpha 0.05, the effect floors and every attack threshold are the shipped ones in
`configs/verification.yaml`. Seeds are below. Each cell is deterministic: I re-ran the `series`
cells and the point-rule numbers reproduced exactly.

## 2. Headline numbers

* **BH under shared columns held its promise.** In all six designs the false discovery proportion
  after BH was between 0.018 and
  0.050 (Monte-Carlo SE 0.005 to 0.015), i.e. at or below 0.05 within about one SE
  everywhere, including the mixed-sign design. Without correction, 8 null claims produced at least one false
  PASS in 26.5% of runs (29.0% mixed-sign).
* **The attacks cost power and remove few false passes.** In the families the gateway PASS
  (BH + attacks) has 0.05 to 0.07 less power than BH alone (e.g. 0.625 to 0.552 at n = 100, rho 0.3) and a false
  discovery proportion lower by 0.005 to 0.013.
* **False kill is the attack set's weak point, and it is A2.** With the shipped rule (A2 on the
  point estimate), a true effect of rho 0.2 to 0.3 that passed the test is broken 6% to 24% of the
  time at n = 60 to 120 on the three clean shapes (0% to 14% at n = 300), almost all of it A2.
* **The evidence rule for A2 added in commit fe42e7d (`break_rule: interval`) is not a free fix.** It cuts that to 0% to 7% on those shapes, but it
  also cuts the detection of a planted late-only effect from 62% / 88% / 96% to 8% / 19% / 51%
  (n = 60 / 120 / 300), and it removes roughly 4 to 11 times fewer luck-passes.
* **Two other attacks have their own false-kill problem** (not changed, section 6): A5 breaks
  29% of true effects (21% to 40% by cell) in the 5%-extreme-values shape, and A3 breaks 14% of true effects when many
  columns are noisy copies of x.

## 3. BH on correlated families, through the real gateway

Eight claims per run, shared columns: a hub column H, three columns T0..T2 (the first `k` follow
H), and five mutually correlated null columns N0..N4; claims are pairs, so null claims share
columns with true ones and with each other. "3 true" means T0..T2 follow H with rho about 0.3 or
0.4; "mixed-sign" negates two of the null columns (the case BH's positive-dependence guarantee
does not formally cover). n is the number of rows handed to the gateway. Power = share of the true
claims that pass.

| design | stage | false discovery proportion (mean +/- MC SE) | any false PASS in a run [95% Wilson] | power (mean +/- SE) |
|---|---|---|---|---|
| 8 claims, all null, n=100 | no correction | 0.265 +/- 0.031 | 26.5% [20.9, 33.0] | - |
| 8 claims, all null, n=100 | BH q < 0.05 | 0.040 +/- 0.014 | 4.0% [2.0, 7.7] | - |
| 8 claims, all null, n=100 | Holm | 0.040 +/- 0.014 | 4.0% [2.0, 7.7] | - |
| 8 claims, all null, n=100 | gateway PASS (BH + floor + attacks) | 0.030 +/- 0.012 | 3.0% [1.4, 6.4] | - |
| 8 claims, all null, mixed-sign columns, n=100 | no correction | 0.290 +/- 0.032 | 29.0% [23.2, 35.6] | - |
| 8 claims, all null, mixed-sign columns, n=100 | BH q < 0.05 | 0.050 +/- 0.015 | 5.0% [2.7, 9.0] | - |
| 8 claims, all null, mixed-sign columns, n=100 | Holm | 0.045 +/- 0.015 | 4.5% [2.4, 8.3] | - |
| 8 claims, all null, mixed-sign columns, n=100 | gateway PASS (BH + floor + attacks) | 0.045 +/- 0.015 | 4.5% [2.4, 8.3] | - |
| 8 claims, 3 true (rho about 0.3), n=100 | no correction | 0.053 +/- 0.009 | 17.0% [12.4, 22.8] | 0.822 +/- 0.015 |
| 8 claims, 3 true (rho about 0.3), n=100 | BH q < 0.05 | 0.018 +/- 0.005 | 6.0% [3.5, 10.2] | 0.625 +/- 0.024 |
| 8 claims, 3 true (rho about 0.3), n=100 | Holm | 0.003 +/- 0.002 | 1.0% [0.3, 3.6] | 0.537 +/- 0.022 |
| 8 claims, 3 true (rho about 0.3), n=100 | gateway PASS (BH + floor + attacks) | 0.010 +/- 0.004 | 3.0% [1.4, 6.4] | 0.552 +/- 0.023 |
| 8 claims, 3 true (rho about 0.3), n=200 | no correction | 0.062 +/- 0.009 | 20.0% [15.0, 26.1] | 0.980 +/- 0.006 |
| 8 claims, 3 true (rho about 0.3), n=200 | BH q < 0.05 | 0.041 +/- 0.008 | 12.5% [8.6, 17.8] | 0.932 +/- 0.011 |
| 8 claims, 3 true (rho about 0.3), n=200 | Holm | 0.018 +/- 0.005 | 6.0% [3.5, 10.2] | 0.872 +/- 0.015 |
| 8 claims, 3 true (rho about 0.3), n=200 | gateway PASS (BH + floor + attacks) | 0.034 +/- 0.007 | 11.0% [7.4, 16.1] | 0.878 +/- 0.014 |
| 8 claims, 3 true (rho about 0.3), mixed-sign nulls, n=200 | no correction | 0.058 +/- 0.009 | 19.0% [14.2, 25.0] | 0.967 +/- 0.007 |
| 8 claims, 3 true (rho about 0.3), mixed-sign nulls, n=200 | BH q < 0.05 | 0.030 +/- 0.007 | 10.0% [6.6, 14.9] | 0.935 +/- 0.010 |
| 8 claims, 3 true (rho about 0.3), mixed-sign nulls, n=200 | Holm | 0.011 +/- 0.004 | 4.0% [2.0, 7.7] | 0.890 +/- 0.013 |
| 8 claims, 3 true (rho about 0.3), mixed-sign nulls, n=200 | gateway PASS (BH + floor + attacks) | 0.023 +/- 0.006 | 8.0% [5.0, 12.6] | 0.865 +/- 0.014 |
| 8 claims, 3 true (rho about 0.4), n=100 | no correction | 0.063 +/- 0.010 | 19.5% [14.6, 25.5] | 0.978 +/- 0.006 |
| 8 claims, 3 true (rho about 0.4), n=100 | BH q < 0.05 | 0.030 +/- 0.007 | 9.0% [5.8, 13.8] | 0.960 +/- 0.008 |
| 8 claims, 3 true (rho about 0.4), n=100 | Holm | 0.013 +/- 0.005 | 3.5% [1.7, 7.0] | 0.918 +/- 0.011 |
| 8 claims, 3 true (rho about 0.4), n=100 | gateway PASS (BH + floor + attacks) | 0.017 +/- 0.005 | 6.0% [3.5, 10.2] | 0.910 +/- 0.012 |

Reading it. "BH q < 0.05" is what the gate calls significant; "gateway PASS" additionally needs
the effect floor and survival of the attacks. The Wilson interval is for the run-level rate (at
least one false PASS in a run of 8); the false discovery proportion is a mean over runs, with its
Monte-Carlo SE.

* BH's false discovery proportion is at most 0.05 in every design. The all-null mixed-sign row
  sits at 0.050 +/- 0.015: with 200 runs it cannot be told apart from anything between 0.02 and
  0.08, so it neither confirms nor refutes control there.
* With 3 true claims, BH leaves 6% to 12.5% of runs with at least one false PASS (Holm 1% to 6%), in line with an FDR
  promise and not an "no false card in this run" promise. If the promise to a user is the second kind, Holm is the
  tool, at the power cost shown (0.625 vs 0.537 at n = 100; 0.932 vs 0.872 at n = 200).
* The attacks remove only a little: PASS vs BH false discovery proportion 0.018 vs 0.010, 0.041 vs 0.034,
  0.030 vs 0.023, 0.030 vs 0.017 in the four "true" designs. In the same designs they take away 0.05 to 0.07 of the power.

Limits: one dependence structure family (a hub plus a shared factor), Spearman claims only, a
family size of 8, 200 runs (SE up to 0.015), 1000 permutations. Different claim types and mixed
permutation schemes in one family were not tried.

## 4. False kill and false survive, per attack and overall

Tables: gate-clearing synthetic tables, each attacked under **both** A2 rules (same table, same
seed, so the comparison is paired). Entries are the share of those tables where **any** attack
broke the claim. Percentages with 95% Wilson intervals; cell entries in the compact tables are
"A2 point / A2 interval" rounded to a whole percent, with 200 tables per cell (an interval of
about +/- 5 points at 20%).

### 4.1 Pooled (all 54 cells)

**Main grid**

| tables that cleared the gate | arm | any check broke | A1 | A2 | A3 | A4 | A5 | A6 | A7 | checks run per table |
|---|---|---|---|---|---|---|---|---|---|---|
| true effect (false KILL) (n=7200) | A2 point (current default) | 20.4% [19.5, 21.3] | 0.1% [0.1, 0.2] | 13.2% [12.5, 14.0] | 3.5% [3.1, 3.9] | 0.5% [0.4, 0.7] | 4.9% [4.5, 5.5] | 0.0% [0.0, 0.1] | 0.0% [0.0, 0.1] | 4.9 |
| true effect (false KILL) (n=7200) | A2 interval (kappa 0.10) | 11.2% [10.5, 12.0] | 0.1% [0.1, 0.2] | 2.4% [2.1, 2.8] | 3.5% [3.1, 3.9] | 0.5% [0.4, 0.7] | 4.9% [4.5, 5.5] | 0.0% [0.0, 0.1] | 0.0% [0.0, 0.1] | 4.8 |
| luck-pass, no effect (false SURVIVE = 1 - this) (n=3600) | A2 point (current default) | 33.1% [31.5, 34.6] | 1.0% [0.7, 1.4] | 25.2% [23.8, 26.6] | 6.5% [5.7, 7.3] | 1.8% [1.4, 2.3] | 1.6% [1.3, 2.1] | 0.0% [0.0, 0.1] | 0.0% [0.0, 0.1] | 4.8 |
| luck-pass, no effect (false SURVIVE = 1 - this) (n=3600) | A2 interval (kappa 0.10) | 15.0% [13.9, 16.2] | 1.0% [0.7, 1.4] | 4.4% [3.8, 5.2] | 6.5% [5.7, 7.3] | 1.8% [1.4, 2.3] | 1.6% [1.3, 2.1] | 0.0% [0.0, 0.1] | 0.0% [0.0, 0.1] | 4.6 |

How to read the pooled rows. They mix shapes I chose, so the pooled number is a summary of my
grid and not an estimate for any real population. The cells are what to look at.

### 4.2 True effects, % broken (A2 point / A2 interval)

| shape | n=60, rho=0.2 | n=60, rho=0.3 | n=120, rho=0.2 | n=120, rho=0.3 | n=300, rho=0.2 | n=300, rho=0.3 |
|---|---|---|---|---|---|---|
| gaussian | 20 / 4 | 18 / 1 | 24 / 3 | 16 / 3 | 12 / 0 | 1 / 0 |
| heavy_tail | 24 / 2 | 16 / 0 | 16 / 3 | 6 / 0 | 4 / 0 | 0 / 0 |
| skewed | 21 / 3 | 18 / 4 | 24 / 7 | 15 / 2 | 14 / 0 | 3 / 0 |
| outliers | 47 / 29 | 42 / 30 | 37 / 26 | 36 / 30 | 49 / 41 | 42 / 40 |
| many_columns | 40 / 28 | 33 / 20 | 34 / 22 | 21 / 11 | 14 / 6 | 2 / 2 |
| series | 21 / 21 | 20 / 20 | 16 / 16 | 12 / 12 | 14 / 14 | 2 / 2 |

On `series` the interval rule has no interval to use (a block-differenced series cannot be
bootstrapped yet), so it falls back to the point rule and the two columns are identical. Before
that fallback existed, the interval rule silently switched A2 off for every time series; the
fallback is part of this branch.

### 4.3 Luck-passes, % broken (A2 point / A2 interval); false survive = 100 minus this

| shape | n=60 | n=120 | n=300 |
|---|---|---|---|
| gaussian | 26 / 4 | 33 / 8 | 22 / 2 |
| heavy_tail | 28 / 3 | 32 / 8 | 34 / 4 |
| skewed | 30 / 8 | 30 / 8 | 30 / 6 |
| outliers | 42 / 21 | 47 / 28 | 41 / 22 |
| many_columns | 44 / 26 | 53 / 36 | 28 / 9 |
| series | 28 / 28 | 26 / 26 | 24 / 24 |

### 4.4 Which attack does it (current point rule), by shape

True effects (false kill):

| shape | tables | A1 | A2 | A3 | A4 | A5 |
|---|---|---|---|---|---|---|
| gaussian | 1200 | 0.0% [0.0, 0.3] | 13.8% [12.0, 15.9] | 1.4% [0.9, 2.3] | 0.4% [0.2, 1.0] | 0.0% [0.0, 0.3] |
| heavy_tail | 1200 | 0.0% [0.0, 0.3] | 10.3% [8.7, 12.2] | 0.6% [0.3, 1.2] | 0.2% [0.0, 0.6] | 0.2% [0.0, 0.6] |
| skewed | 1200 | 0.5% [0.2, 1.1] | 13.4% [11.6, 15.5] | 1.4% [0.9, 2.3] | 0.7% [0.3, 1.3] | 0.2% [0.0, 0.6] |
| outliers | 1200 | 0.2% [0.0, 0.6] | 15.3% [13.4, 17.5] | 3.3% [2.5, 4.5] | 1.4% [0.9, 2.3] | 29.2% [26.7, 31.9] |
| many_columns | 1200 | 0.0% [0.0, 0.3] | 12.2% [10.4, 14.1] | 14.2% [12.4, 16.3] | 0.4% [0.2, 1.0] | 0.0% [0.0, 0.3] |
| series | 1200 | 0.0% [0.0, 0.3] | 14.3% [12.5, 16.4] | 0.0% [0.0, 0.3] | 0.0% [0.0, 0.3] | 0.0% [0.0, 0.3] |

Luck-passes (broken, so *not* surviving):

| shape | tables | A1 | A2 | A3 | A4 | A5 |
|---|---|---|---|---|---|---|
| gaussian | 600 | 0.0% [0.0, 0.6] | 23.0% [19.8, 26.5] | 2.5% [1.5, 4.1] | 2.0% [1.1, 3.5] | 0.0% [0.0, 0.6] |
| heavy_tail | 600 | 0.0% [0.0, 0.6] | 27.0% [23.6, 30.7] | 3.0% [1.9, 4.7] | 2.0% [1.1, 3.5] | 0.2% [0.0, 0.9] |
| skewed | 600 | 0.8% [0.4, 1.9] | 25.2% [21.9, 28.8] | 3.8% [2.6, 5.7] | 1.3% [0.7, 2.6] | 0.7% [0.3, 1.7] |
| outliers | 600 | 5.3% [3.8, 7.4] | 26.2% [22.8, 29.8] | 7.7% [5.8, 10.1] | 3.2% [2.0, 4.9] | 9.0% [7.0, 11.6] |
| many_columns | 600 | 0.0% [0.0, 0.6] | 24.0% [20.8, 27.6] | 21.8% [18.7, 25.3] | 2.2% [1.3, 3.7] | 0.0% [0.0, 0.6] |
| series | 600 | 0.0% [0.0, 0.6] | 25.7% [22.3, 29.3] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] |

A6 and A7 never fired here (no such flaw was planted; A6 needs a time structure and A7 an exact
identity). A4 is rare. The false kills are A2 (every shape), A5 (`outliers`) and A3 (`many_columns`).

### 4.5 Worked illustration (arithmetic on the pooled numbers, not a measurement)

Suppose 10% of the claims that clear BH are luck-passes (an assumed share, to show the mechanism).
* No attacks: 10.0% of the surviving claims are luck-passes and every true claim is kept.
* With A2 on the point rule (shipped): 8.5% are luck-passes and 79.6% of the true claims are kept.
* With A2 on the interval rule: 9.6% are luck-passes and 88.8% of the true claims are kept.
The attack set as shipped buys about 1.5 points of purity for the loss of about a fifth of the true claims on these shapes. Its value is in the *mechanisms* it catches (section 5), not in clearing luck.

## 5. A planted flaw A2 exists for: the effect lives only in the late months

Twelve months, rho 0.7 inside the last four months and none before (overall rho about 0.23),
gate-clearing tables, A2 splits by period. A "break" here is the right answer.

**Late-only flaw**

| tables that cleared the gate | arm | any check broke | A1 | A2 | A3 | A4 | A5 | A6 | A7 | checks run per table |
|---|---|---|---|---|---|---|---|---|---|---|
| planted late-only effect (should be broken) (n=600) | A2 point (current default) | 82.3% [79.1, 85.2] | 0.0% [0.0, 0.6] | 82.2% [78.9, 85.0] | 1.5% [0.8, 2.8] | 0.8% [0.4, 1.9] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 4.9 |
| planted late-only effect (should be broken) (n=600) | A2 interval (kappa 0.10) | 26.0% [22.7, 29.7] | 0.0% [0.0, 0.6] | 24.0% [20.8, 27.6] | 1.5% [0.8, 2.8] | 0.8% [0.4, 1.9] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 4.3 |
| planted late-only effect (should be broken) (n=600) | A2 interval (kappa 0.2) | 35.8% [32.1, 39.7] | 0.0% [0.0, 0.6] | 34.3% [30.6, 38.2] | 1.5% [0.8, 2.8] | 0.8% [0.4, 1.9] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 4.4 |
| planted late-only effect (should be broken) (n=600) | A2 interval (kappa 0.4) | 49.3% [45.3, 53.3] | 0.0% [0.0, 0.6] | 48.8% [44.9, 52.8] | 1.5% [0.8, 2.8] | 0.8% [0.4, 1.9] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 4.6 |

| shape | rho | n | cleared | A2 point (current default) | A2 interval (kappa 0.10) | A2 interval (kappa 0.2) | A2 interval (kappa 0.4) |
|---|---|---|---|---|---|---|---|
| late_only | 0.7 | 60 | 200 | 62.5% [55.6, 68.9] | 8.0% [5.0, 12.6] | 12.5% [8.6, 17.8] | 21.5% [16.4, 27.7] |
| late_only | 0.7 | 120 | 200 | 88.0% [82.8, 91.8] | 19.0% [14.2, 25.0] | 31.5% [25.5, 38.2] | 49.5% [42.6, 56.4] |
| late_only | 0.7 | 300 | 200 | 96.5% [93.0, 98.3] | 51.0% [44.1, 57.8] | 63.5% [56.6, 69.9] | 77.0% [70.7, 82.3] |

And on true constant effects (Gaussian cells, n 60 / 120 / 300, rho 0.2 / 0.3), the same arms:

**Gaussian cells, three interval budgets**

| tables that cleared the gate | arm | any check broke | A1 | A2 | A3 | A4 | A5 | A6 | A7 | checks run per table |
|---|---|---|---|---|---|---|---|---|---|---|
| true effect (false KILL) (n=1200) | A2 point (current default) | 16.1% [14.1, 18.3] | 0.0% [0.0, 0.3] | 14.3% [12.5, 16.4] | 2.1% [1.4, 3.1] | 0.1% [0.0, 0.5] | 0.0% [0.0, 0.3] | 0.0% [0.0, 0.3] | 0.0% [0.0, 0.3] | 4.9 |
| true effect (false KILL) (n=1200) | A2 interval (kappa 0.10) | 2.2% [1.6, 3.3] | 0.0% [0.0, 0.3] | 0.1% [0.0, 0.5] | 2.1% [1.4, 3.1] | 0.1% [0.0, 0.5] | 0.0% [0.0, 0.3] | 0.0% [0.0, 0.3] | 0.0% [0.0, 0.3] | 4.8 |
| true effect (false KILL) (n=1200) | A2 interval (kappa 0.2) | 2.2% [1.6, 3.3] | 0.0% [0.0, 0.3] | 0.1% [0.0, 0.5] | 2.1% [1.4, 3.1] | 0.1% [0.0, 0.5] | 0.0% [0.0, 0.3] | 0.0% [0.0, 0.3] | 0.0% [0.0, 0.3] | 4.8 |
| true effect (false KILL) (n=1200) | A2 interval (kappa 0.4) | 3.0% [2.2, 4.1] | 0.0% [0.0, 0.3] | 0.8% [0.5, 1.5] | 2.1% [1.4, 3.1] | 0.1% [0.0, 0.5] | 0.0% [0.0, 0.3] | 0.0% [0.0, 0.3] | 0.0% [0.0, 0.3] | 4.8 |
| luck-pass, no effect (false SURVIVE = 1 - this) (n=600) | A2 point (current default) | 29.5% [26.0, 33.3] | 0.0% [0.0, 0.6] | 25.0% [21.7, 28.6] | 3.2% [2.0, 4.9] | 2.5% [1.5, 4.1] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 4.8 |
| luck-pass, no effect (false SURVIVE = 1 - this) (n=600) | A2 interval (kappa 0.10) | 5.7% [4.1, 7.8] | 0.0% [0.0, 0.6] | 0.2% [0.0, 0.9] | 3.2% [2.0, 4.9] | 2.5% [1.5, 4.1] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 4.6 |
| luck-pass, no effect (false SURVIVE = 1 - this) (n=600) | A2 interval (kappa 0.2) | 6.0% [4.4, 8.2] | 0.0% [0.0, 0.6] | 0.5% [0.2, 1.5] | 3.2% [2.0, 4.9] | 2.5% [1.5, 4.1] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 4.6 |
| luck-pass, no effect (false SURVIVE = 1 - this) (n=600) | A2 interval (kappa 0.4) | 8.0% [6.1, 10.4] | 0.0% [0.0, 0.6] | 2.5% [1.5, 4.1] | 3.2% [2.0, 4.9] | 2.5% [1.5, 4.1] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 0.0% [0.0, 0.6] | 4.6 |

| shape | rho | n | cleared | A2 point (current default) | A2 interval (kappa 0.10) | A2 interval (kappa 0.2) | A2 interval (kappa 0.4) |
|---|---|---|---|---|---|---|---|
| gaussian | 0.2 | 60 | 200 | 26.0% [20.4, 32.5] | 3.5% [1.7, 7.0] | 3.5% [1.7, 7.0] | 4.5% [2.4, 8.3] |
| gaussian | 0.2 | 120 | 200 | 26.5% [20.9, 33.0] | 5.5% [3.1, 9.6] | 5.5% [3.1, 9.6] | 7.0% [4.2, 11.4] |
| gaussian | 0.2 | 300 | 200 | 11.0% [7.4, 16.1] | 0.0% [0.0, 1.9] | 0.0% [0.0, 1.9] | 1.0% [0.3, 3.6] |
| gaussian | 0.3 | 60 | 200 | 19.0% [14.2, 25.0] | 2.5% [1.1, 5.7] | 2.5% [1.1, 5.7] | 3.0% [1.4, 6.4] |
| gaussian | 0.3 | 120 | 200 | 12.0% [8.2, 17.2] | 2.0% [0.8, 5.0] | 2.0% [0.8, 5.0] | 2.5% [1.1, 5.7] |
| gaussian | 0.3 | 300 | 200 | 2.0% [0.8, 5.0] | 0.0% [0.0, 1.9] | 0.0% [0.0, 1.9] | 0.0% [0.0, 1.9] |
| gaussian | 0.0 | 60 | 200 | 30.0% [24.1, 36.7] | 5.0% [2.7, 9.0] | 5.5% [3.1, 9.6] | 9.0% [5.8, 13.8] |
| gaussian | 0.0 | 120 | 200 | 31.5% [25.5, 38.2] | 8.5% [5.4, 13.2] | 9.0% [5.8, 13.8] | 10.0% [6.6, 14.9] |
| gaussian | 0.0 | 300 | 200 | 27.0% [21.3, 33.5] | 3.5% [1.7, 7.0] | 3.5% [1.7, 7.0] | 5.0% [2.7, 9.0] |

Reading the two together, per rule (A2 breaks only):

| A2 rule | breaks a TRUE effect | breaks a LUCK-PASS | catches the planted late-only flaw |
|---|---|---|---|
| A2 point (current default) | 14.3% [12.5, 16.4] | 25.0% [21.7, 28.6] | 82.2% [78.9, 85.0] |
| A2 interval (kappa 0.10) | 0.1% [0.0, 0.5] | 0.2% [0.0, 0.9] | 24.0% [20.8, 27.6] |
| A2 interval (kappa 0.2) | 0.1% [0.0, 0.5] | 0.5% [0.2, 1.5] | 34.3% [30.6, 38.2] |
| A2 interval (kappa 0.4) | 0.8% [0.5, 1.5] | 2.5% [1.5, 4.1] | 48.8% [44.9, 52.8] |

The true-effect and luck-pass columns come from the Gaussian cells of the sensitivity run; the
flaw column from the late-only cells. The three interval budgets sit on one curve: the knob trades
false kill against detection, and the "budget" named `false_kill_budget` is a nominal level, not the
rate you get (the achieved false-kill of the A2 rule is 0.1% to 0.8% where the nominal budget is 10% to 40%).
The point rule is the high-detection, high-false-kill end. There is no setting in these runs that has both low
false kill and high detection, at these sample sizes.

## 6. Decision

| Question | Decision | Why (numbers above) |
|---|---|---|
| Flip `attacks.break_rule` to `interval`? | **No. Default stays `point`.** | It lowers false kill from 6-24% to 0-7% at n 60-120, but late-only detection falls from 62/88/96% to 8/19/51% and luck-passes removed fall from 22-34% to 2-8%. That trades a miss of a real flaw for fewer lost findings; which is right depends on how often a user's table has an effect that lives in part of its history, which I cannot measure. A weaker check on the PASS side is the owner's call, not a number I can tune (prime directive, section 0). The flag stays for the owner. |
| Change the interval rule's parameters? | No. | `false_kill_budget` 0.4 detects more of the flaw (49% vs 24% of A2 breaks) at 0.8% false kill, so it is the better setting *if* the owner flips the rule. The shipped 0.10 is left so that nothing changes by accident. |
| Interval rule on a block-differenced series | **Changed (flag off).** Falls back to the point rule and records it in `details.fallback`. | The flag silently switched A2 off for every time series (it returned "no interval is available"). A check that vanishes when a flag flips is not what the flag says it does. |
| "Held up" label | **Changed (wording only).** Always "survived K of M further checks that could be run", the number that could not tell, "little checked" when M is below `attacks.min_capacity` (2), and the columns-in-this-table-only limit. | In every cell of the grid the mean number of checks that ran was 4.0 to 5.9 per table, so "little checked" (M < 2) did not occur on these shapes; it exists for tables where most checks do not apply. |
| FRAGILE wording | **Changed (wording only).** Names the check that broke the claim, states K of M that survived, and says a broken check is not proof the claim is false. | A2 breaks a true effect 6-24% of the time at small n on clean shapes, so a break must not read as "the claim is wrong". |
| A5 (alternative statistic sign) and A3 (one control, searched among many) | **Not changed.** Findings only. | A5 broke 29% of true effects (21% to 40% by cell) when 5% of rows are extreme, and A3 broke 14% when 9 columns are noisy copies of x. Both rules compare a point estimate with a line; each deserves its own interval rule and its own planted-flaw measurement, and I have neither. No delegation covered redesigning them. |
| BH | **Unchanged.** | Section 3. No design exceeded 0.05 beyond one SE. |
| Alpha, effect floors, attack thresholds | Unchanged. | |

Also added, no verdict effect: the chat reply states the chance that at least one of the chat
claims tested on the dataset passed by luck (1 - (1 - alpha)^k), with a known-answer test.

## 7. Reproduce

From the repo root (Python 3.13, `pip install -e .` and `pip install -r requirements/verification.txt -r requirements/dev.txt -r requirements/runtime.txt`), 4 cores:

```
python scripts/calibration/gate_report_card.py --v2 attacks     --reps 200 --workers 4 --out artifacts/gate_card_attacks.json       # seed 20261027, about 45 min
python scripts/calibration/gate_report_card.py --v2 flaws       --reps 200 --workers 4 --out artifacts/gate_card_flaws.json         # seed 20261029, about 5 min
python scripts/calibration/gate_report_card.py --v2 sensitivity --reps 200 --workers 4 --out artifacts/gate_card_sensitivity.json  # seed 20261029, about 30 min
python scripts/calibration/gate_report_card.py --v2 families    --reps 200 --workers 4 --permutations 1000 --out artifacts/gate_card_families.json  # seed 20261025, about 75 min
python scripts/calibration/gate_report_card.py --v2 cross-check --reps 300 --out artifacts/gate_card_crosscheck.json              # seed 20261028
python scripts/calibration/render_gate_calibration.py artifacts > tables.md
```

The raw JSON of the runs reported here is in `docs/evidence/gate_calibration_2026-10-25/`.
The earlier `--reps 100` base card and the colleague's `--extra` card are unchanged.
Plumbing tests (tiny replicate counts, not calibration): `tests/unit/verification/test_gate_report_card.py`.

### Stand-in check

The attack grids gate with a Spearman test, not the gateway, to make thousands of tables
affordable. On Gaussian tables with n = 120 and rho 0.3, each arm on its own fresh tables, 300 draws:

| | tables cleared | attacks broke the claim |
|---|---|---|
| real gateway (n = 120) | 273 of 300 | 33 (12.1% [8.7, 16.5]) |
| stand-in (n = 120) | 277 of 300 | 37 (13.4% [9.8, 17.9]) |

## 8. What this does and does not show

* Everything is synthetic and was built by the author of the gate. The shapes are plausible, not
  representative. A different mix of shapes moves the pooled numbers; the per-cell numbers are the
  evidence.
* The attack grids use a stand-in gate (a Spearman test at a family of one claim) and not the full
  gateway, apart from the family part and the check above. The gateway's 50/50 split, BH over
  several claims and effect floor are therefore not in the false-kill rates. In a family the
  final PASS rows (section 3) are the end-to-end numbers.
* The gate-clearing tables are a selected set: passing the test inflates the full-sample effect that A2
  compares the halves with (winner's curse). That is how the gateway runs too, and it is part of why A2 breaks true
  effects at small n; it is not removed here.
* "True" effects are modest (rho 0.2 and 0.3). At rho 0.4 or above or n above 300 the false-kill rates
  are small, as the repo's older card found (0 of 100 at rho about 0.4, n = 200).
* 200 tables per cell: an interval of about +/- 5 points at 20%, +/- 2 at 3%. Differences of a few points between cells are
  noise. Several cells were looked at; none was picked to look good.
* Flaw detection was measured for one flaw (a late-only effect) at one strength (rho 0.7 in the last third). Detection of a
  measured confounder (A3) and a Simpson reversal (A4) was measured in the earlier research note (98-100%), not here;
  detection of an unmeasured confounder is zero by construction.
* Nothing here tests real data, other claim types (group differences, trends, period changes), or the
  `cluster` and `paired` schemes.
