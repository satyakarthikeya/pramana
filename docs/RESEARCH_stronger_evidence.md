# Research note: can PRAMANA prove a claim, and what is stronger evidence than "passed a corrected test and survived the attacks"?

Status: RESEARCH. No source, config or test was changed. Written 2026-10-24 on branch
`docs/satya/research-stronger-evidence`, on top of `docs/RESEARCH_verification_agent.md` (the
"previous note"; I do not repeat its BH and attack results, I build on them). Anything below that
touches p-values, FDR, the attack rule, the split, a contract or the memory guard needs the
verification owner (AGENTS.md section 8.10) and is marked **[OWNER]**. Stance: blunt.

How to read the evidence. **Code** = I read it in `src/pramana/verification/` and `configs/`.
**Computed** = closed-form arithmetic I ran (appendix `calc.py`). **Simulated** = a small
simulation I wrote (appendix `sim.py`; planted synthetic tables, 150 gate-passing tables per
cell except the luck-pass rows, which are 51 to 76; so each rate carries a standard error of
about 0.03 to 0.07; the gate is approximated by a Fisher-z test plus the 0.10 floor, not the
real gateway). **Literature** = found by web search on 2026-10-24 and read as a search
summary or abstract, never the full paper, unless I say otherwise. Where a claim comes from my
general knowledge and I fetched no source, I say so.

---

## 0. The answer to the owner's question

**No. A single uploaded table cannot prove a claim true, and no check we can add will change that.**
What a table can establish is narrower, and some of it really is provable:

| Level | Statement | Can a table establish it? | How |
|---|---|---|---|
| L0 Computation | "The code computed rho = 0.31 on these 214 rows with seed S." | **Yes, exactly.** Re-execute the stored code and seed: identical numbers. | `spec_hash`, logged seed, stored test (AGENTS.md 3.4). This is the only thing the word "proof object" honestly covers. |
| L1 Sample pattern | "In the held-back rows, x and y move together more than chance shuffling usually produces (q = 0.012)." | **Yes**, as a probability statement about the shuffle null, not as certainty. | Permutation test plus BH. The error rate is bounded (FDR 0.05), never zero. |
| L2 Robustness | "The pattern did not disappear under K of M specified perturbations." | **Yes**, for the perturbations listed. | Attacks A1-A7. Says nothing about perturbations not listed. |
| L3 Population association | "x and y are associated in the population this table came from." | **No.** Only if the rows are a random draw from a stated population, which the tool does not know and cannot check. | A convenience sample, a scraped file, or an NHANES extract analysed without survey weights does not estimate a population quantity (survey weights: general knowledge, no source fetched). |
| L4 Causal | "x changes y." | **No, never from one table.** Requires assumptions about what is not in the table (no unmeasured confounding, correct time order, no selection on the outcome). | Hernan argues causal aims should be stated, not hidden behind "association" (summary only, https://pmc.ncbi.nlm.nih.gov/articles/PMC5888052). Even then the identification assumptions come from outside the data. |
| L5 Generalisation | "This will hold in another year, region or sample." | **No.** Only an independent sample can speak to it. | Fresh-sample replication (section 1), which the tool can only simulate by sacrificing rows. |

Three more honest limits:

1. **Every null hypothesis of "exactly zero association" is nearly always false at large n.** With
   enough rows almost any pair of real-world columns is associated by some route (selection,
   shared causes, measurement). The effect floors in `configs/verification.yaml` exist for that
   reason (the config comment says so). A tiny q at n = 2000 therefore proves little about
   whether anyone should care. (The "crud factor" is Meehl's term; general knowledge, no source fetched.)
2. **A survivor is not a confirmed claim.** Popper's point (summary: https://www.encyclopedia.com/humanities/encyclopedias-almanacs-transcripts-and-maps/popper-karl-raimund-1902-1994)
   and Mayo and Spanos's severity requirement (https://errorstatistics.com/wp-content/uploads/2013/12/2006mayo_spanos_severe_testing.pdf, summary only):
   failure to break a claim counts as evidence only to the degree the check could have broken it.
3. **The word "proof" is itself a thesis-review liability.** The owner just asked "can we PROVE
   it?" because the product says "proof object", "PASS" and "verified". The contract name can stay
   (renaming it is a contract change, 8.7); the user-facing copy should say **evidence record** and
   **held up**.

### 0.1 How to word each level (code-written sentences; no model)

| Level | Allowed sentence (template) | Banned |
|---|---|---|
| L1 | "In the held-back rows, higher {x} goes with higher {y} (rank correlation 0.31, 214 rows). Chance shuffling this strong in about 1 run in 80 (q = 0.012)." | "proves", "confirms", "is true", "significant" without the number |
| L2 | "It held up: 4 of 5 checks that could be run did not weaken it; 1 could not tell (too few rows in a subgroup). Checked against the columns in this table only." | "robust" without K, M, N; "validated" |
| L3 | "This describes these rows. If they are a fair sample of {population the user names}, the pattern is likely there too. The tool cannot check that." | "in the population", "people with X have Y" |
| L4 | "This is an association. It does not show that {x} changes {y}. A column not in this table could produce it (section 4 gives how strong that would have to be)." | "causes", "leads to", "effect of", "drives" (the Explainer already bans causal vocabulary) |
| L5 | "Nothing here tests whether this holds in new data." | "will", "generalises" |

This is the cheapest improvement in the note and needs no new statistics (rank A in section 9).

---

## 1. Fresh-sample replication, and what a third partition costs

### 1.1 What exists (code)

`schemes.split_rows` already divides rows 50/50 (`confirmation_fraction: 0.5`): exploration rows
choose claims, confirmation rows are the only rows the gate tests. Attack A2 then halves the
confirmation rows again (so a "split-half consistency" check runs at n/4 per half). The
exploration half is not used as evidence at all after claim selection. That design is the
correct one for post-selection validity (section 5); the cost is that the gate already runs at half
power.

### 1.2 Computed: power of the gate today versus a three-way split

Spearman, two-sided, alpha = 0.05 per stage, Fisher-z approximation with variance 1.06/(n-3)
(a standard approximation; I did not verify it against the repo's permutation test), **no BH
correction, no effect floor**, so real gate power is lower than shown. "n" is total uploaded rows.
"Today" = confirmation half (n/2). "3-way" = one third confirm (n/3). "Both" = a result that must be
significant on the confirm third AND on a separate replication third (the product of the
two powers).

| rho | n | Today (n/2) | 3-way confirm (n/3) | Both (confirm and replicate, n/3 each) |
|---|---|---|---|---|
| 0.2 | 60 | 0.18 | 0.13 | 0.02 |
| 0.2 | 100 | 0.27 | 0.19 | 0.04 |
| 0.2 | 200 | 0.49 | 0.35 | 0.12 |
| 0.2 | 500 | 0.87 | 0.71 | 0.50 |
| 0.2 | 1000 | 0.99 | 0.95 | 0.90 |
| 0.3 | 60 | 0.35 | 0.24 | 0.06 |
| 0.3 | 100 | 0.54 | 0.38 | 0.14 |
| 0.3 | 200 | 0.84 | 0.67 | 0.45 |
| 0.3 | 500 | 1.00 | 0.97 | 0.94 |
| 0.4 | 60 | 0.57 | 0.40 | 0.16 |
| 0.4 | 100 | 0.81 | 0.62 | 0.38 |
| 0.4 | 200 | 0.98 | 0.90 | 0.81 |
| 0.1 | 1000 | 0.58 | 0.42 | 0.18 |
| 0.1 | 2000 | 0.87 | 0.71 | 0.50 |

Plain reading:

* **Below about 500 rows a real replication check would reject most true effects.** At n = 100,
  rho = 0.3 a requirement of "significant twice" passes 14% of true claims. That is a worse false-kill rate than A2's 16%
  measured in the previous note, for a stronger-sounding label.
* **At n of about 800 to 1000 and above, rho 0.2 and up, a genuine replication costs little**
  (0.90 at rho 0.2, n = 1000), and then "replicated in an independent third of the rows" is a
  real, defensible sentence. For rho = 0.1, even n = 2000 gives only 0.50.
* The cost also hits claims that never reach replication: moving confirmation from n/2 to n/3
  lowers gate power for every claim (0.54 to 0.38 at n = 100, rho 0.3). A third partition must
  therefore be **conditional on n** (an adaptive split decided by n alone, never by the observed effect),
  or it makes the product worse for the student-sized tables that are its main audience.
* **Replication should be judged on direction and estimate, not on a second p < 0.05.** Standard
  advice (general knowledge; no source fetched) is to ask whether the replication estimate is
  compatible with the discovery estimate, because a significance-twice rule is the lowest-power way to
  ask. A cheap version: same sign and the replication estimate above the effect floor halved. I did
  not simulate its false-kill rate; it would need the card (section 8).
* **Winner's curse.** The estimate on the rows that passed the gate is inflated by selection.
  Gelman and Carlin's Type S (wrong sign) and Type M (exaggeration) errors are the standard
  description (summary: https://sites.stat.columbia.edu/gelman/research/published/PPS551642_REV2.pdf).
  Showing the exploration-half estimate beside the confirmation estimate is free, but the exploration
  rows chose the claim, so it is a descriptive "expect the effect to look smaller on fresh data", never evidence.

### 1.3 Literature on the splitting cost

* Single splits are noisy ("p-value lottery"): Meinshausen, Meier, Buhlmann, *P-values for high-dimensional regression*
  aggregate over many splits (summary: https://stat.ethz.ch/Manuscripts/buhlmann/pvaluesJASA2009.pdf).
  Aggregation is **incompatible with a held-back set that must stay untouched**: each re-split reuses rows, which is exactly the
  reuse problem the previous note flagged (A7).
* Wasserman and Roeder's screen-and-clean uses one half to select and the other to test
  (https://arxiv.org/pdf/0704.1139, summary). PRAMANA's split is this procedure.
* A 2025 split-sample CLT paper (https://arxiv.org/pdf/2511.04957, summary) reports that cross-fitting
  has higher power than a single split, because both halves play both roles. Cross-fitting needs
  an estimand that does not depend on which half chose it; for a selected claim that is not our case.
* Rinaldo, Wasserman, G'Sell on sample splitting for assumption-lean inference
  (https://arxiv.org/abs/1611.05401v2): I saw only the abstract; it does not tell us the power loss we need.

### 1.4 Verdict on replication

Build it only for large tables, flagged, owner-approved (rank F). For everything else keep the label
**"split-half consistency"** (as the previous note says), never "replicated".

---

## 2. Statistical truth, robustness, causal truth

See the ladder in section 0. The one addition: **robustness is a property of a claim under listed
perturbations, not a probability that the claim is true.** The 4-of-5 in "held up" is a count of
checks, not a probability; a "severity score" or "confidence 87%" built from it would invent a number
(previous note, B4). Also, A3 (partial out a measured control) is **not a causal adjustment**: partialling
out a collider or a mediator can create or hide association (general knowledge; Hernan, link above, discusses the causal framing). Its
sentence must stay "after accounting for column Z in this table".

---

## 3. Negative controls and placebo tests that need no user input

### 3.1 The real idea and why code-only versions are weak

A negative control outcome (or exposure) is a variable that cannot be caused by the exposure but
shares its likely biases; finding an "effect" on it signals confounding or bias (Lipsitch,
Tchetgen Tchetgen, Cohen, *Negative controls*: https://pmc.ncbi.nlm.nih.gov/articles/PMC3053408/ , summary).
The method depends on knowing, from outside the data, that no causal path exists. **PRAMANA
does not know that**, and must not guess it, because a wrongly assumed "null" column turns a real
effect into a false alarm (a later source cited in the search summary also notes negative controls
can lack sensitivity and specificity for the bias they target).

### 3.2 Code-only versions

| Version | What it does | Needs user knowledge? |
|---|---|---|
| **Decoy rank** | Compute the same statistic on pairs of columns the claim did not name; report where the claim's |rho| ranks among them. | No. Decoys are "unrelated" only by assumption. |
| **Row-order placebo** | Re-run the claim after shuffling rows within blocks of the stated order (time, entity), or against a lagged copy. A claim that survives a shifted, impossible relation is suspect. | Needs an order column; the structure detector already finds one. |
| **Declared-null column** | The user marks one column "this should have no link". | **Needs user input.** Out of scope (the owner said the tool may not ask). |
| **Permutation reference** | Already the gate. | n/a |

### 3.3 Simulated: what the decoy rank can and cannot do

Rule tested: pass if the claim's |rho| beats the 90th percentile of |rho| over the other
27 pairs in an 8-column table. 150 gate-passing tables per cell (51 to 76 for luck passes).

| Scenario (gate passed) | n | Decoy check lets it pass | Would be killed |
|---|---|---|---|
| True rho 0.3 | 100 / 200 / 500 | 1.00 / 1.00 / 1.00 | 0% (0 false kills) |
| No effect, luck pass | 100 / 200 / 500 | 0.99 / 0.99 / 1.00 | about 0 to 1% |
| All columns share a row-order drift, no real link | 100 / 200 / 500 | 0.06 / 0.15 / 0.12 | 85% to 94% |
| One unmeasured column drives both x and y | 100 / 200 / 500 | 1.00 / 1.00 / 1.00 | 0% |

**Findings, stated plainly:**

* The decoy rank is a **shared-structure detector**, not a luck detector: it almost never
  rejects a chance pass (the decoys are drawn from the same noise the test already used) and
  it never sees an unmeasured common cause. It catches one specific, real failure: a table where
  everything correlates with everything because of a shared trend, batch or ordering. In this synthetic setup that failure is
  detected 85% to 94% of the time with zero false kills on a true effect. The admissibility code may already catch
  ordered data on tables with a time column; I did not measure the overlap.
* So its value is one planted mechanism, which the previous note's attacks cover only partly. It is **report-only material**
  ("this claim is no stronger than {k}% of other pairs in your table"), not a PASS rule.
* The gate's own comment in `configs/verification.yaml` already shows decoy pairs at 0.28 to 0.30 against a true 0.33 on
  NHANES, so the same lesson holds on real data: the effect size alone does not separate signal from background.

---

## 4. Sensitivity to unmeasured confounding

### 4.1 What the literature offers

* **E-value** (VanderWeele and Ding, *Sensitivity analysis in observational research: introducing the E-value*,
  Annals of Internal Medicine 2017; summary only: https://dash.harvard.edu/bitstream/handle/1/36874927/EValue_FinalSubmission.pdf):
  the minimum strength of association, on the risk-ratio scale, an unmeasured confounder would need with both exposure and
  outcome to fully explain away the association; recommended for the point estimate and for the confidence limit
  nearest the null. Formula (general knowledge, standard): E = RR + sqrt(RR(RR-1)) for RR above 1.
  For continuous outcomes Linden's documentation gives RR approximately exp(0.91 d) with d the standardised difference
  (https://ageconsearch.umn.edu/record/340347/files/Linden.pdf , summary). There is **no source I found** for converting
  a Spearman rho; the conversion below (d = 2r / sqrt(1 - r^2), then the RR step) is mine, approximate,
  and not validated for ranks.
* **Ding and VanderWeele 2016**, *Sensitivity analysis without assumptions*: a bounding factor with two
  sensitivity parameters and no assumption on the unmeasured confounder's form (summary: https://ar5iv.arxiv.org/html/1507.03984).
* **Cinelli and Hazlett 2020**, *Making sense of sensitivity: extending omitted variable bias*, JRSS-B: the robustness value
  (the partial R-squared a confounder would need with both treatment and outcome to bring the estimate to zero), computable from a
  t-statistic and degrees of freedom, with the `sensemakr` package (summary: https://ideas.repec.org/a/bla/jorssb/v82y2020i1p39-67.html).
  The covariate-benchmarking idea (compare the needed strength to the strongest measured covariate) is described in related work I saw
  only as a title, https://ar5iv.labs.arxiv.org/html/2306.10562.
* **Rosenbaum bounds** (Rosenbaum, *Observational Studies*, 2002; software summary: https://cran.r-project.org/web/packages/rbounds/refman/rbounds.html):
  Gamma is the odds of differential assignment to a binary treatment due to hidden factors; the output is a worst-case p-value bound
  per Gamma and a "critical Gamma". The package covers Wilcoxon signed-rank (matched) and rank-sum. **For continuous exposure
  there is no drop-in for Spearman**; the dose-model extensions are for matched studies (https://arxiv.org/pdf/2401.06909, summary).

### 4.2 Fit to PRAMANA

| Claim type | Rosenbaum Gamma | E-value | Partial-correlation tipping point |
|---|---|---|---|
| Two-group difference (Cliff's delta) | Possible in principle (rank-sum bounds), but Gamma means "odds of being in group A rather than B", which is meaningless for sex, region, year. 8 h, hard to explain. | Approximate (d from delta is a further approximation). | Via point-biserial: approximate. |
| Rank correlation | **Not available** | Approximate, my conversion | **Best fit** |
| Trend, cluster, paired, differenced schemes | No | No | No. The null has non-standard dependence; say "not available" rather than force it. |

### 4.3 The sentence code can honestly produce (Pearson-scale, approximate for ranks)

For a correlation r_xy, an unmeasured column u with correlations a with x and b with y gives the
partial correlation (r_xy - a b) / sqrt((1 - a^2)(1 - b^2)) (general knowledge, standard identity; I did not search for it).
Setting a = b, the strength needed to bring the association to a target t is

    a = sqrt( (r_xy - t) / (1 - t) )

| Observed rho | needed a = b to reach 0 | to reach the 0.10 floor | n = 100 interval lower end of the same rho |
|---|---|---|---|
| 0.2 | 0.45 | 0.33 | interval includes 0 (no strength needed) |
| 0.3 | 0.55 | 0.47 | lower end 0.104: about 0.32 |
| 0.4 | 0.63 | 0.58 | n = 60: lower end 0.155: about 0.39 |

Template: *"A column that is not in this table would need to be correlated about 0.55 with both
{x} and {y} to account for all of this association (about 0.32 at the low end of its
interval). The strongest column in this table is correlated 0.41 with {x} and 0.28 with {y}. That is a size
check, not evidence that such a column exists or does not."*

Honest limits of this sentence:

* It assumes one unmeasured factor, linear dependence, and equal strength; for ranks it is an approximation I did not simulate
  (the appendix computes E-value and tipping numbers only; a rank-based check would be the known-answer test).
* It says nothing about reverse direction, selection into the sample, measurement error, or colliders.
* Reading it as "so it is probably causal" is the abuse to guard against: a table where the strongest measured column is also about 0.45
  is exactly where it is least reassuring. The benchmark clause must always print.
* The E-value is a more famous name for the committee; the tipping-point version is easier to explain to students and is exact in the Pearson
  case. If a name matters, print both, but label the E-value conversion "approximate".

**Verdict:** yes, a short, honest sentence is producible by code. It is descriptive, never gating. It makes
the causal gap visible and quantified instead of merely disclaimed (rank C).

---

## 5. Selective inference, data splitting, conformal, e-values

PRAMANA already has the strongest simple answer: the analyst may look at up to 300 pairs on the exploration rows,
and the gate tests only the shown claims on independent confirmation rows (previous note, A1). Conditional on the selection,
the confirmation p-values are valid because the rows are independent of the choice. That is the data-splitting solution. So:

| Method | Source (summary only unless stated) | What it buys | Fit | Verdict |
|---|---|---|---|---|
| Selective inference, conditional on selection | Fithian, Sun, Taylor, *Optimal inference after model selection* https://arxiv.org/pdf/1410.2597 | More power than splitting, exact for exponential families after a known selection rule | Needs the analyst's selection rule written as a mathematical event. Ours is an LLM and heuristic choice. | Do not build |
| Randomised splitting / data fission | Rasines and Young https://arxiv.org/pdf/2102.02159 ; Leiner, Duan, Wasserman, Ramdas, JASA 2025 https://ideas.repec.org/a/taf/jnlasa/v120y2025i549p135-146.html | Split a single data point with noise, keeping both pieces informative | Parametric assumptions; the previous note already rejected it for dependent data | Do not build |
| Multi-split aggregation | Meinshausen et al. (link in 1.3) | Removes the split lottery | Reuses the held-back rows; breaks the "touched once" story | Do not build |
| Reusable holdout / thresholdout | Dwork et al., https://cis.upenn.edu/~aaroth/reusable.html (project page) | Many adaptive looks at one holdout | Time splits cannot be redrawn; real exposure is cross-run reuse (A7) | Disclosure now, maybe later |
| e-values, anytime-valid | Ramdas, Grunwald, Vovk, Shafer https://arxiv.org/abs/2210.01948v2 ; Vovk and Wang https://arxiv.org/pdf/1912.06116 ; Wang and Ramdas e-BH https://arxiv.org/abs/2009.02824v4 | Independent e-values multiply; any-time validity; FDR control under arbitrary dependence | Permutation p-values are not e-values. Useful only for **evidence across runs and chat** (a running product per dataset) | Research track, **[OWNER]**, rank G |
| Conformal selection | Jin and Candes (listed in https://par.nsf.gov/servlets/purl/10538790 ; title not confirmed) | FDR for selecting units whose label exceeds a threshold, needs a calibration set | Answers "which rows", not "is this column pair related" | Not applicable |
| Knockoffs | Barber and Candes https://arxiv.org/pdf/1404.5609 | Exact FDR for which **variables** matter in a linear model, any correlation among them | Fixed-X needs n at least p. Targets "which of these 20 columns predicts y", a different claim from pairwise association | Maybe as a chat feature much later |
| Forking paths | Gelman and Loken, named at https://en.wikipedia.org/wiki/Forking_paths_problem (PDF not read) | A data-dependent choice is a hidden multiplicity | Each data-dependent choice inside the attack stage is a fork | Fix the menu, count M (previous note, B7) |

**Honest conclusion:** none of these is the next best thing to build. The most valuable action in this area is documentation:
state in the report why the split gives post-selection validity (section 5 first paragraph), and where it does not (reruns on the same held-back rows,
chat). That costs about an hour (rank I).

---

## 6. Cross-validated predictive checks

Idea: does x improve out-of-sample prediction of y beyond the other columns? Stone's cross-validation
(https://sites.stat.washington.edu/courses/stat527/s13/readings/Stone1974.pdf, listing) is the base; Lei et al.'s leave-one-covariate-out (LOCO) importance
compares prediction error with and without a covariate (summary: https://arxiv.org/pdf/1604.04173).

### 6.1 Simulated (appendix `sim.py`)

Rank-transformed linear model, 5-fold CV, out-of-fold R-squared gain from including x, p-value by permuting x
(99 permutations), on the same rows that passed the gate; 6 other noise columns.

| Scenario (gate passed) | n | LOCO p < 0.05 (corroborated) |
|---|---|---|
| True rho 0.3 | 100 / 200 / 500 | 0.82 / 0.98 / 1.00 |
| Luck pass | 100 / 200 / 500 | 0.46 / 0.61 / 0.63 |
| Shared drift, no link | 100 / 200 / 500 | 0.10 / 0.35 / 0.54 |
| One unmeasured column drives both | 100 / 200 / 500 | 0.99 / 1.00 / 1.00 |

### 6.2 What it means

* **Not independent corroboration.** It uses the rows the test used. Its p-value is a close relative of the
  Spearman p-value, so a claim whose p sits just under 0.05 fails it about half the time. At n = 100 it removes 54% of luck passes and 18% of true ones. That trade-off
  is what a stricter alpha would give; I did not test that equivalence, so treat "consistent with" as my reading.
* **It does not see an unmeasured confounder** (99% to 100% survival).
* **It can add value when the table has a measured confounder:** the question "does x add predictive value beyond z" is the CV analogue of A3, and
  I did **not** simulate that case (my other columns were noise), so I do not claim a number for it.
* **Its real use is a different sentence**, not a stronger verdict: "Knowing {x} improves out-of-sample prediction of {y} by 6%
  beyond the other columns" is a useful, honest effect-size statement for a student. Report-only, n at least 200.
  It is not a proof of anything about truth.

---

## 7. Triangulation

Lawlor, Tilling, Davey Smith define triangulation as combining approaches **with different and unrelated biases**
(Int J Epidemiol 2016; summary: https://pmc.ncbi.nlm.nih.gov/articles/PMC5841843). Within one table, every estimator sees the
same rows and the same confounding. Spearman, Kendall, a trimmed correlation, a partial correlation and a CV gain are correlated views of one
sample, so agreement among them is **estimator agreement, not triangulation**, and the number of agreeing estimators is not a measure of strength
(A5 already does a version of this). Do not multiply their evidence and do not use the word "triangulated" in the product.
Honest uses: (a) flag a claim where estimators disagree in sign or collapse, (b) report the range of estimates. Real triangulation needs an
external source (a second table, a known instrument), which the tool may not ask for. Skip it.

---

## 8. How to show each added check helps

### 8.1 Definitions per check c

* **False kill FK(c)**: P(c breaks or demotes a claim | gate PASS, effect real). Lower is better.
* **False survive, mechanism FS-m(c)**: P(claim survives | gate PASS, planted flaw f). Lower is better. Planted flaws: measured confounder,
  Simpson reversal, row-order drift (section 3), extreme points, leakage/identity, entity-driven effect, **unmeasured confounder** (target is 0 detection; reported as a limit, never tuned).
* **False survive, chance FS-c(c)**: P(claim survives | gate PASS, no effect).
* **Added value of a check** = paired difference: the same tables run with and without c, FS-m and FK each as a difference with a paired interval.
  Report both together so a check cannot look good by killing everything.
* **Capacity**: share of PASS claims where fewer than 2 checks could run (the previous note's label).

### 8.2 Designs

| Design | Purpose | Detail |
|---|---|---|
| **Planted effects** | FK | n in {60, 100, 200, 500, 1000}, rho in {0.2, 0.3, 0.4}, free / stratified / cluster schemes, 20 extra correlated columns present. 1000 replicates per cell; Wilson interval. |
| **Planted flaws** | FS-m | One generator per flaw next to `tests/unit/verification/test_attacks.py` cases. At least 0.9 detection for measured flaws (targets from the previous note, B8). |
| **A/A test** | Validity | Run the card with the check switched on but unable to act (shadow mode). Verdict must be identical to the baseline in 100% of runs. This is the test that proves a report-only check cannot touch the prime directive. |
| **Pure-null real tables** | FS-c | Take a real table (NHANES demo, the retail table), shuffle each column independently by row (keeps marginals), run the full gateway, count PASS and survivors. Expected PASS about alpha per family, by BH. |
| **Semi-synthetic spike** | FK on real data | Replace y by y_rank + beta * x_rank on a real table with beta in a small grid; same measurement. |
| **Decision rule fixed beforehand** | Avoid tuning to the demo | Adopt a verdict-changing check only if FS-m improves by at least 0.10 on a named flaw AND FK rises by at most 0.02 at n at least 100, rho at least 0.3, measured with SE at most 0.01 (1000 replicates gives SE 0.01 near a rate of 0.1). Report-only checks need only the A/A test and the card row. |

### 8.3 Replicate budget

SE of a rate p with R replicates is sqrt(p(1-p)/R): R = 300 gives 0.017 to 0.029 at p = 0.1 to 0.3 (the
precision of my own sims; too coarse to adopt anything), R = 1000 gives 0.01, R = 2000 gives 0.007. The previous note's 12-minute
prototype runs at 300; a CI card at 1000 per cell must be budgeted (about an hour of compute, my estimate, not measured).

### 8.4 What would convince a committee

A single figure: rows = checks (gate only, + attacks, + each candidate), columns = FK, FS-m by flaw, FS-c, with the
"unmeasured confounder" column shown at zero detection for every row. It tells the true story: the tool catches the
flaws it can see and does not claim the ones it cannot.

---

## 9. Ranked options

Value is my 1 to 5 for a thesis review (credibility gained per hour of honest, defensible content). "Hours" is a
first version, including tests. V/H = value divided by hours. "Owner" = needs the verification owner under 8.10
(or is a contract change under 8.7 that affected owners must hear about).

| Rank | Option | Value | Hours | V/H | Files that would change | Risk to `memory_write => verdict == PASS` | Owner (8.10) |
|---|---|---|---|---|---|---|---|
| **A** | **Evidence ladder wording** (L0 to L5, "cannot show" line, "evidence record" copy, ban list) | 5 | 1.5 | 3.3 | Explainer/code sentence templates, web copy, docs. No `verification/` change. | None: wording only | Tell the owner (new statistical disclosure); not a gate change |
| **I** | **Document why the split gives post-selection validity** and where it fails (reruns, chat) | 2 | 1 | 2.0 | `docs/` only | None | No |
| **B** | **Report card: FK / FS / A/A rows** (previous note E1 item 1; prerequisite for any verdict-changing check) | 5 | 3.5 | 1.4 | `scripts/calibration/gate_report_card.py`, `tests/unit/verification/test_gate_report_card.py` | None | Thresholds only |
| **C** | **Confounding-strength sentence** (tipping point, benchmarked to the strongest measured column; section 4.3) | 4 | 4 | 1.0 | New `src/pramana/verification/sensitivity.py`; `configs/verification.yaml` (benchmark settings); `gateway.py` (call after attacks, as the interval and power notes are); `src/pramana/contracts/proof_object.py` (new optional descriptive field; precedent: `effect_interval`, power note); `tests/unit/verification/test_sensitivity.py` | None if it never feeds the verdict; add a test that verdict and memory decision are identical with it on or off | **Yes**: contract change (8.7) and a new statistic text; descriptive only, not a p-value or FDR change |
| D | Decoy rank / shared-structure report (section 3.3) | 2.5 | 3 | 0.8 | `verification/` new helper, config, same contract field style | None if report-only | Yes (contract), no for the wording |
| K | Estimator-agreement line (sign and range of 3 estimators) | 1.5 | 2.5 | 0.6 | `attacks/runner.py` helpers, proof text | None if report-only | Yes if it can break |
| E | Cross-validated incremental prediction, report-only (section 6) | 2.5 | 6 | 0.4 | New helper, config (folds, permutations), contract field | None if report-only | Yes (contract) |
| F | Third partition for n of about 800 or more (section 1) | 3 | 10 | 0.3 | `schemes.py` (`split_rows`), `config.py`, `configs/verification.yaml`, `spec.py`, gateway, tests; changes confirmation power for every run above the threshold | Changes who is tested. A failed replication only demotes (ratchet lowers); memory rule untouched, but must be re-proved by test | **Yes** (split, p-values, spec) |
| G | Per-dataset e-value / online-FDR ledger for reruns and chat | 3 | 12 to 15 | 0.2 | `looks.py`, `chat/service.py`, new ledger module, contracts | Touches what counts as PASS across runs; must keep `verdict == PASS` as a precondition | **Yes** (FDR, multiplicity) |
| H | Rosenbaum Gamma for two-group claims | 1.5 | 8 | 0.2 | New module, config, contract | Same as C | Yes |
| X | Knockoffs, conformal selection, selective inference, data fission, multi-split | 1 | 15+ each | below 0.1 | n/a | Reusing held-back rows or changing the family correction | Yes |

Two cautions on the ranking. First, **A, I, B and C change no verdict**, so none of them can create a path for an
unverified insight to reach memory; the A/A test in 8.2 makes that a checked property. Second, **anything that can kill a claim
(D, E, F, K as breakers) loses to B in order**: the previous note showed a plausible-looking check already kills 16% of true
claims at student sizes, so no new killer ships without its FK/FS row.

---

## 10. Risks specific to this note

1. A sentence like section 4.3's can be read as reassurance ("a confounder would have to be that strong, so it is probably real"). Mitigation: always print the
   benchmark and the "size check, not evidence" clause; never print it on a claim where fewer than 2 checks ran.
2. Showing the exploration-half estimate beside the confirmation one invites a reader to treat it as replication. Label it "chose the claim; expect it to shrink".
3. A model must not write any of section 0.1 or 4.3. They are code templates; the Explainer rules stay as written.
4. Do not report FK/FS/power numbers in the thesis from this note: they are from small synthetic runs with approximations. Only the card, once built, supplies reportable numbers.

---

## 11. Ten-line summary and recommendation

1. A table can establish: exact computation (L0), a chance-bounded pattern in these rows (L1), and survival of listed perturbations (L2). It cannot establish population truth, cause, or generalisation.
2. "Proof" is the wrong word for the product; use **evidence record / held up**; keep the contract name.
3. Fresh-sample replication costs too much power below about 500 rows: requiring significance twice passes only 14% of true rho 0.3 claims at n = 100 (computed); it is affordable at n of about 800 or more for rho 0.2 and up.
4. Negative controls need outside knowledge; the code-only decoy rank detects shared drift (85% to 94%, simulated) but not luck passes and not an unmeasured common cause.
5. Unmeasured-confounding sensitivity is the most honest new content: a code sentence, "a missing column would need correlation about 0.55 with both columns (about 0.32 at the interval's low end) to explain this away", benchmarked to the strongest measured column; approximate for ranks.
6. Rosenbaum Gamma does not fit rank correlation or non-treatment groups; the E-value needs an approximate conversion with no source I found for ranks.
7. Selective inference, data fission, conformal and knockoffs add nothing here: the existing explore/confirm split already gives post-selection validity; the gaps are reruns and chat, and only the ledger/e-value track (owner decision, 12+ h) addresses them.
8. A cross-validated predictive check is not independent of the test (same rows): at n = 100 it removes 54% of luck passes and 18% of true ones, which looks like a stricter alpha; its use is a "predicts X% better" sentence, report-only.
9. Triangulation within one table is estimator agreement, not triangulation; do not use the word.
10. Any check that can kill a claim must ship with a paired FK/FS/A/A card first (design in section 8); check-it-first ranks above every killer.

**Recommended single next addition: C, the confounding-strength sentence (about 4 h), shipped inside the A wording ladder (about 1.5 h).**
It is the only item that attacks the biggest honest gap (everything the table cannot see) with a number a student can read, it is
descriptive so it cannot touch `memory_write => verdict == PASS` (prove it with the A/A test), and every other candidate here either
duplicates the permutation test, costs power below 500 rows, or needs the card (B) first. B (3.5 h) should follow immediately, because it is
what lets any later killing check be justified with numbers.

---

## Limits of this note

* Sources were read as search summaries; a handful (Rosenbaum 2002, Cox 1975, the SEP entry on Popper) I could not read or find, and
  I do not cite what I did not find. Summary-only items are marked.
* My two scripts use synthetic tables, approximate gates (Fisher-z), one claim type, a handful of noise columns and 51 to 150 tables per cell. The
  numbers show where to look; they are not report-grade.
* The rank-correlation conversions in section 4 are unvalidated for ranks.
* I did not run the repo test suite (documentation-only change) and changed no source, config or test.

---

## Appendix: scripts (not in the repo tree; scratch copies)

`calc.py` (stdlib `math` and numpy only) produced the power and tipping numbers; `sim.py` (numpy only) produced the decoy and LOCO tables. Seeds fixed (`default_rng(11)`).
Reproduce: `python3 -I calc.py` and `python3 -I sim.py`. Core definitions:

```python
# power of a Spearman test, Fisher-z approximation, two-sided alpha
def power(rho, n, alpha=0.05):
    se = (1.06 / (n - 3)) ** 0.5; z = atanh(rho) / se; c = 1.959964
    return sf(c - z) + cdf(-c - z)

# tipping point: strength a = b of an unmeasured column to bring rho down to target t
def tipping(rho, t=0.0):
    return ((rho - t) / (1 - t)) ** 0.5

# decoy rank: pass if |rho_xy| exceeds the q-th quantile of |rho| over every other pair in the table
# LOCO: out-of-fold R2 (5-fold, ranks, OLS) with x minus without x; p by permuting x, 99 permutations
```
