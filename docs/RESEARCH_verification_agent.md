# Research note: does the gateway need Benjamini-Hochberg, and what would a "try to prove it wrong" verification agent be?

Status: RESEARCH. No source, config or test was changed. Written 2026-10-24 against `main` at
`bb5bb77` (PR 31 merged). Every change this note suggests that touches p-values, FDR, the
attack rule or the contracts needs the verification owner under AGENTS.md section 8.10; each is marked
**[OWNER]**. Author's stance: blunt, and not defending code because it exists.

How to read the evidence. "Code" means I read it in `src/pramana/verification/`. "Measured" means I
ran a small simulation on this machine using the repo's own attack code (appendix); those tables are
planted synthetic data that I wrote, with 150 to 300 replicates, so each rate carries a standard
error of about 0.01 to 0.04. "Literature" means I found it by web search on 2026-10-24 and read the
search summary or abstract, not the full paper; the claims are marked where that matters.

---

## 0. The answers in ten lines

1. **BH: keep it.** Some correction is needed (uncorrected, a run of 8 null claims has a 29% chance
   of at least one false PASS, a run of 24 has 57%; measured). BH is the right default for a
   student/analyst audience; Holm is the right swap if the promise ever becomes "no false card in this run".
2. **BH's weak spot is not dependence, it is what it does not cover:** chat claims (each a family of
   one, so the correction is the identity), and the union of PASSes over repeated runs on the same
   held-back rows. The report card tests neither, nor BH itself (it runs with `m_max = 1`).
3. **Dependence between claims** (shared columns): in the one structure I tried, BH kept FDR at
   or below 0.043 at alpha 0.05. Not proof. No replacement is justified until a wider card says so.
4. **"Try to prove it wrong, otherwise it stands" is already the shape of the gateway** (test, then attacks, one-way
   ratchet). It is right in structure and wrong in calibration.
5. **The wrong part:** an attack breaks a claim on a noisy point estimate, not on evidence. Measured: after
   passing the gate, a true effect (rho 0.2 to 0.3, n 60 to 200) is killed 4% to 21% of the time,
   almost always by A2 (split-half). That is killing a claim without proving it wrong.
6. **The other wrong assumption:** attacks do not catch chance passes. Of claims that passed on pure noise,
   only 23% to 29% were broken. Attacks catch specific mechanisms (measured confounder, Simpson reversal: 98% to
   100%), not luck. BH and the attacks are not substitutes.
7. **"Stands" can honestly mean one thing:** it passed a multiplicity-corrected test and K of M applicable checks, which
   could have found a flaw, did not. It is not proof, replication, or cause. Call it **held up** (the v3 word) and
   always show K, M and "N could not tell".
8. **A literal "stands unless disproved" agent with no positive-evidence stage is wrong for this product:** on
   thin data nothing can disprove anything, so everything would stand. Mayo's severity point.
9. **Model role:** DeepSeek may suggest extra columns to check from a closed menu (already built, off) and word
   the result; code decides everything else. Honest value of the model here is small.
10. **First step:** extend the report card with a correlated family of 8 and attack false-kill / false-survive
    rows (about 3.5 h, changes no verdict). Section E.

---

## A. Benjamini-Hochberg in this tool

### A1. What it does here (code)

* `gateway.verify_batch_with_summary` tests every admissible claim, collects all raw permutation p-values, calls
  `apply_bh` once, then gates (`q < alpha` AND effect at or above the metric floor AND direction). The family
  is the set of claims that were actually tested in one run; screened-out claims are excluded
  (`gateway.py` lines near 916-950; `fdr.py`).
* Family size: V1 hands the gateway at most **8** claims (`configs/v1.yaml: max_candidates: 8`); the
  planner and workspace agent are capped at 6 to 8 (`configs/analysis.yaml`); the hard ceiling is
  `m_max = 40`, and the loader refuses a config whose permutation count could not resolve a
  p-value small enough to survive BH at that size (`config.py` near line 275). `n_permutations = 10000`.
* The claims are chosen on the **exploration** half and tested on the **confirmation** half
  (`schemes.split_rows`). That matters: the analyst may look at up to 300 column pairs
  (`max_hypotheses_examined`) and none of those looks enters the family, which is legitimate only because the
  confirmation p-values are independent of the selection. So the family size is the number of claims
  shown, not the number searched. This is a correct and underrated design choice.
* **Chat** sends claims one at a time; each is a family of one, so `q = p` (STATUS.md, AGENTS.md section 2). Up to
  `max_tests_per_dataset = 50` per dataset, ever (`configs/analysis.yaml`, `chat/service.py`).
* The report card (`scripts/calibration/gate_report_card.py`, `pinned_config`) sets `m_max = 1` and tests
  "a family of one claim". By construction it cannot show anything about BH or about correlated
  families. The sign-off sheet says so itself (GATEWAY_V3_STATUS_AND_SIGNOFF.md section 4).

### A2. How correlated are the claims

Very, by construction: the claims in a run share columns (the same BMI in three claims, the same
revenue in four), and different claims use different nulls (free shuffle, stratified, cluster,
block-differenced). Two structural facts follow:

* Two-sided rank-correlation p-values that share a column are dependent. For one-sided Gaussian tests,
  BH's guarantee needs positive regression dependence (PRDS); the summary I found says it does not
  formally cover two-sided tests with arbitrary correlation (Benjamini and Yekutieli 2001, as summarised
  in the Project Euclid abstract page and an online-FDR paper, below).
* Because claims have different null schemes, there is **no single joint permutation** that
  shuffles every claim consistently. That rules out the natural Westfall-Young max-T
  correction (below) without a large redesign.

### A3. What the literature gives (all found 2026-10-24; summaries, not full papers)

| Method | Guarantee | Fit to this tool |
|---|---|---|
| BH step-up | FDR at most alpha when p-values are independent or PRDS | Fits an exploratory, disclosed audience. Two-sided dependence is covered by simulation evidence, not proof. |
| BY (BH at alpha / H_m) | FDR control under arbitrary dependence | Costs a factor of 2.7 at m = 8 and 4.3 at m = 40 (harmonic numbers). Measured power loss below. |
| Holm / Bonferroni | Family-wise error (P(any false)) | Valid under any dependence, simplest to explain, loses power. |
| Westfall-Young max-T, Romano-Wolf | FWER with the dependence respected; needs subset pivotality (Romano-Wolf drop it) | Needs one joint resampling of all claims. Not available across five different null schemes. |
| e-BH (Wang and Ramdas) | FDR under any dependence, no penalty | Needs e-values; permutation p-values are not e-values. Research track, not a quick change. |
| Online FDR: alpha-investing, LORD++, SAFFRON | FDR (or mFDR) over a stream of tests; guarantees need independence or a stated non-negative-dependence condition | The right tool for a user who runs many analyses over time, and for chat. Not needed inside one run. |

Sources actually found:

* Benjamini and Yekutieli, *The control of the false discovery rate in multiple testing under dependency*,
  Annals of Statistics 29(4): https://projecteuclid.org/euclid.aos/1013699998 (abstract page; PRDS and
  the harmonic-number fix as summarised by the search result).
* Reiner-Benaim, *FDR control by the BH procedure for two-sided correlated tests with implications to
  gene expression data analysis*, Biometrical Journal 2007 (listing only):
  https://www.bgu.ac.il/en/researcher/anat-reiner-benaim/publications/78213189/ . The search result reports
  it is simulation evidence, not a theorem.
* **A caution I could not verify:** an unreviewed 2026 preprint claims BH can fail to control FDR for
  correlated two-sided Gaussian tests in a factor model for large numbers of hypotheses: "The
  Benjamini-Hochberg Procedure Can Fail to Control the FDR for Correlated Two-Sided Gaussian Tests",
  https://arxiv.org/pdf/2607.12208 . I did not read it. At m of 8 to 40 with permutation p-values I would
  not act on it; the planned experiment (A6) is what would show a problem here.
* Wang and Ramdas, *False discovery rate control with e-values*:
  https://arxiv.org/pdf/2009.02824v2 .
* Ramdas, Yang, Wainwright, Jordan, *Online control of the false discovery rate with decaying memory*
  (LORD++): https://arxiv.org/pdf/1710.00499 .
* Foster and Stine, *Alpha-investing: a procedure for sequential control of expected false discoveries*
  (controls mFDR, a weaker criterion than FDR): https://repository.upenn.edu/handle/20.500.14332/47482 .
  Fisher's arXiv paper shows SAFFRON and LORD also control FDR under non-negative dependence:
  https://arxiv.org/pdf/2110.08161v1 .
* Westfall-Young max-T and its step-down version: lecture-style description and the `multtest` manual
  page found at https://dk-01.installer.hardenedbsd.org/bioconductor/packages/2.3/bioc/manuals/multtest/man/mt.maxT.Rd ;
  Romano and Wolf on the subset-pivotality assumption: https://econ-papers.upf.edu/papers/727.pdf .
  Holm's procedure: no source fetched; stated from general knowledge.

### A4. Measured: BH under shared columns, against the alternatives

Setup (`bh_sim2.py`, appendix; seed 7; 300 replicates per row; 999 permutations; Spearman, two-sided,
the same kind of test the gate uses, run directly, **not** through the gateway). A hub column H; three
columns T_i linked to H; five mutually correlated "null" columns that are independent of H and T.
Claims are pairs, so nulls share columns with true claims and with each other. alpha = 0.05.
"Any false" is P(at least one false PASS in a run). FDR is the mean false share of rejections. SE of an FDR cell near 0.01.

| Case | Method | FDR | Any false | Power |
|---|---|---|---|---|
| m = 8, all null, n = 100 | none | 0.293 | 0.293 | |
| | BH | 0.043 | 0.043 | |
| | Holm | 0.037 | 0.037 | |
| m = 8, 3 true (rho about 0.29), n = 100 | none | 0.071 | 0.210 | 0.82 |
| | BH | 0.027 | 0.080 | 0.64 |
| | BY | 0.008 | 0.020 | 0.46 |
| | Holm | 0.015 | 0.033 | 0.56 |
| m = 8, 3 true (rho about 0.41), n = 100 | BH | 0.031 | 0.103 | 0.94 |
| | Holm | 0.010 | 0.033 | 0.89 |
| m = 8, 3 true (rho about 0.41), n = 60 | BH | 0.029 | 0.083 | 0.75 |
| | Holm | 0.019 | 0.053 | 0.68 |
| m = 24, all null, n = 100 | none | 0.570 | 0.570 | |
| | BH | 0.043 | 0.043 | |
| m = 24, 3 true (rho about 0.29), n = 100 | none | 0.193 | 0.463 | 0.80 |
| | BH | 0.033 | 0.070 | 0.45 |
| | BY | 0.003 | 0.007 | 0.13 |
| | Holm | 0.031 | 0.037 | 0.36 |
| m = 24, 3 true (rho about 0.41), n = 100 | BH | 0.040 | 0.117 | 0.91 |
| | Holm | 0.009 | 0.027 | 0.81 |

What this says, plainly:

* **Needed, yes.** Without correction the run-level chance of a false card is 29% (m = 8) to 57% (m = 24) under pure noise.
* **Dependence did not break BH here.** FDR stayed at or below 0.043 with alpha 0.05 in every cell. It is conservative
  (about 0.03) because most claims are null and p-values are discrete. Limits: one dependence structure
  (positive, shared hub), Spearman only, one permutation count, 300 replicates. No negative correlations, no
  mixed schemes. That is exactly what the planned experiment adds.
* **BH versus Holm is a trade, not a verdict.** At m = 8, BH gains 0.05 to 0.09 of power over Holm
  (0.64 vs 0.56 at rho 0.29). At m = 24, 0.09 to 0.11. In return, BH leaves 7% to 12% of runs with at
  least one false PASS, against 3% to 5% for Holm. Holm is not wrong; it is a different promise.
* **BY is over-kill here**: it loses 9% to 71% of the power (0.94 to 0.85 in the easiest cell, 0.45 to 0.13 in the hardest) for a guarantee nothing measured says we need.
* **Bonferroni** behaved like Holm and is dominated by it.

### A5. Decision

| Option | Right when | Verdict for PRAMANA |
|---|---|---|
| **Keep BH inside a run** | Promise is "few false cards on average", audience reads cards with caveats, runs are small (at most 8 to 40) | **Recommended. Right today.** |
| Switch to Holm | Promise becomes "no false card in this run", e.g. results quoted in a report without the reader seeing caveats | Choose if the owner answers "FWER" in question D1. About 25 lines; no new theory. |
| Switch to BY | Experiment A6 shows BH FDR above alpha plus 2 SE under realistic dependence | Fallback only. Do not pre-empt. |
| Westfall-Young / e-BH | Joint resampling across claims; e-values | **Do not build.** Infeasible across five null schemes; no evidence it is needed. |
| Drop correction | Never | Wrong. |
| Online FDR (LORD++, SAFFRON, alpha-investing) | A user runs many analyses on one dataset over time, or chat grows past a demo | Right later, for chat and for a per-dataset ledger. Parked by the owner on 2026-10-24 (v3 decision 4). I agree with parking it, with the two cheap disclosures in A7. |

**The user-visible cost.** A false PASS shows a student a confident card that is wrong, and it can enter
memory; a missed finding shows "not enough evidence at this sample size" and the user can rerun with more
data. For this audience a false PASS costs more than a miss, which argues for FDR 0.05 as a ceiling
and not for loosening. It does not argue for BY: its power cost lands on true findings the user would have
wanted.

### A6. The experiment that settles it

* **Design.** Extend `gate_report_card.py` (**[OWNER]** for thresholds only; measurement changes no verdict) with
  family scenarios run through the real gateway, `m_max = 8` and `24`, template generator, 2000 permutations:
  (a) the hub design above; (b) a mixed-sign design with negatively correlated null columns (the case PRDS does
  not cover); (c) a family that mixes schemes (free, stratified, cluster); (d) all-null. Arms: none, BH (current),
  Holm, BY.
* **Data.** Planted synthetic tables, fixed seeds, n in {60, 100, 200}, rho in {0.2, 0.3, 0.4}, true share in {0, 3/8, 6/8}.
  Then NHANES demo columns shuffled by row to create real-distribution nulls.
* **Command (once the scenarios exist).** `python scripts/calibration/gate_report_card.py --families --reps 2000 --out artifacts/gate_report_card_families.json`.
  Today's prototype: `python bh_sim2.py` from the appendix, about 12 minutes.
* **Expected.** BH FDR at or below 0.05 in every cell, about 0.02 to 0.045; BH minus Holm power gain of 0.05 to 0.10 at m = 8; BY power loss of 0.1 to 0.3.
* **A bad result.** BH FDR above 0.065 in any cell at 2000 replicates (SE about 0.005): switch the family to Holm (or BY if power
  matters and Holm is too costly). Any cell where the assigned scheme differs from the planted one: that is a
  bug in `assign_plan`, not a BH problem.

### A7. What BH does not cover (and two cheap disclosures)

* **Chat.** 50 claims per dataset, each at `q = p`. Chance of at least one false PASS among k all-null chat claims: 30% at k = 7,
  92% at k = 50 (1 - 0.95^k). The proof is disclosed "as asked after seeing results", but nothing scales the threshold.
  Cheapest honest fix: show "claim k of 50 on this dataset; if everything asked so far were unrelated, the chance of at least one
  false PASS by now is X%". Text only. Real fix is the parked online-FDR ledger **[OWNER]**.
* **Reruns.** The planner proposes different claims each run (GATEWAY_V3_STATUS_AND_SIGNOFF.md section 4), all tested on
  the same held-back rows. Each run's family is corrected alone. If five runs each had 8 null claims, the chance of at least one false PASS
  in the union is 23% (1 - 0.95^5), and memory takes the union. `looks.py` counts reuse but only discloses it.
* **Dobriban-type worry aside, these two are the real multiplicity holes**, not dependence between claims.

Reusable holdout, for the reuse problem: Dwork, Feldman, Hardt, Pitassi, Reingold, Roth, *The reusable
holdout*, https://cis.upenn.edu/~aaroth/reusable.html (project page and Google Research blog summary; I did not read the Science paper).

---

## B. The "try to prove it wrong" agent

### B1. Mapping the idea onto what exists

| Idea | Exists as | Honest status |
|---|---|---|
| State the claim before looking | Claims come from exploration rows; `spec_hash` (S4) | Covers test code, seed, permutation count, scheme, split digest, direction, alpha (`spec.py`). It does **not** cover the attack menu, thresholds, or the interval settings. Calling it pre-registration would overclaim; it is tamper evidence for what the proof records. |
| Hold out rows | 50/50 split; confirmation rows only for the gate | Fine. Rows are reused across runs and chat (W1; `looks.py` counts, discloses). |
| Try to break it | A1-A7 (`attacks/runner.py`) | Seven fixed attacks, applicable ones only (S3). A1 trims extreme rows; A2 early/late or random halves; A3 partial out one measured control; A4 subgroup sign reversal; A5 alternative statistic sign; A6 first differences; A7 identity/leakage. |
| One failure kills it | `_attacked` in `gateway.py`: any BROKEN turns PASS into REJECT / FRAGILE, never stored | Correct for the invariant (the ratchet only lowers; `memory_write => verdict == PASS` is untouched). Wrong in how BROKEN is decided (B3). |
| Model suggests where to look | `refuter.py` (S8), off by default | Adds controls / grouping columns only, validated against the table, capped at 2 and 2; fails closed. Sound design. |
| Report the attempt | `AttackResult` list on the proof; "HELD UP / NOT ROBUST" wording | There, but not as "K of M could have found a flaw". |
| Placebo / negative control | none | Missing. |
| Specification curve | A3 + A5 + A1 + A4 are a hand-picked mini-multiverse, not a curve | Partly there, no joint reading. |
| Leave-one-out | A1 trims by value; no leave-one-entity-out | Missing for panels (CLUSTER scheme needs only 6 entities; one entity can carry the result). |
| Replication on held-out rows | A2 re-splits the same confirmation rows | The only available "replication" halves the power. Not a replication in the usual sense. |
| Confounder search | A3 (one control, `min_confound_score`), Skeptic (descriptive), refuter (+2) | Measured columns only; one control at a time. |

### B2. What "it stands" can honestly mean

Popper's point, as summarised in the sources I found, is that a surviving hypothesis is not confirmed, only
**corroborated** (https://www.encyclopedia.com/humanities/encyclopedias-almanacs-transcripts-and-maps/popper-karl-raimund-1902-1994 ;
the SEP entry did not come up). Mayo and Spanos add the working condition: failing to find a flaw counts as
evidence only if the test had a high capacity to find the flaw were it there (weak severity principle,
https://errorstatistics.com/wp-content/uploads/2013/12/2006mayo_spanos_severe_testing.pdf , summary only).

Applied here, "could not prove it wrong, so it stands" means exactly this, and no more:

> For this table, with the declared null: the association is unlikely under chance at FDR 0.05 and above its size floor, AND each of K
> perturbations that could actually be run (of M applicable) left the effect on the same side and not collapsed, AND N perturbations were too
> noisy to tell. Checked against the columns in this table only. Not shown: unmeasured confounding, other populations or years, a fresh sample,
> or cause.

Name for it: **held up** (v3 word, keep it). Never "proven", "correct", "validated", "replicated", "true". The strongest
true sentence is "survived K of M checks that could have found a problem". Always print K, M and N.

Two consequences:

1. **A "stands unless disproved" agent with no positive-evidence stage is wrong for this product.** With n = 20 and a noisy effect, no
   attack can disprove anything, so everything would stand. The gate (q below alpha, effect floor) is the positive stage and cannot be dropped. The existing
   order (evidence for, then attempts against) is right. Attacks that did not run, or that were too noisy to tell, must count for neither side; S3's
   `applicable` flag already separates "does not apply" from "could not run". A third state, "too noisy to tell", is missing.
2. **The attack stage is where the current design is wrong.** See B3.

### B3. Measured: what the attack stage actually does

Setup (`atk_sim.py`, appendix; seeds fixed; the repo's own `run_attacks` with the shipped thresholds; correlation
claim, free scheme; a table is kept only if a Spearman test says p below 0.05 and |rho| at least 0.10, which stands in for the gate at a family of one; 150 gate-passing tables per cell).
"Killed" means any attack returned BROKEN.

**True effects wrongly killed (after passing the gate):**

| n | rho 0.2 | rho 0.3 | rho 0.4 |
|---|---|---|---|
| 60 | 17% | 20% | 10% |
| 100 | 21% | 16% | 7% |
| 200 | 15% | 4% | 1% |
| 400 | 6% | 1% | 0% |

Nearly all kills are A2 (e.g. n = 100, rho 0.2: 29 A2 breaks and 4 A4 breaks among 150 tables). The repo's own test pins the kill rate at most 15% only for rho about
0.4 at n = 100 and 400 (`test_attacks.py`); it is not tested where student data lives (n 60 to 200, rho 0.2 to 0.3). Mechanism (code): A2
compares the **worse of two noisy half estimates** with the full-sample estimate and breaks if it falls below half of it
(`shrink_fraction 0.5`), with no allowance for the half's sampling error, and the full-sample estimate is itself inflated by selection on
passing the gate. This is not "proving the claim wrong"; it is a coin biased by sample size.

**Chance passes (no real effect, passed the gate by luck) that the attacks remove:**

| n | passed / 900 tables | killed |
|---|---|---|
| 60 | 46 | 24% |
| 100 | 45 | 29% |
| 200 | 40 | 23% |
| 400 | 35 | 23% |

So about three quarters of luck-passes survive the attacks, and the kills that do happen are the same noisy A2. **The attacks are not a second line against false positives.**
That is what BH is for, and why the two cannot stand in for each other.

**Planted mechanisms (gate-passing tables):**

| Flaw | n | Killed | By |
|---|---|---|---|
| Confounded by a measured column | 100 / 400 | 100% / 100% | A3 |
| Simpson reversal across a measured group | 100 / 400 | 98% / 100% | A4 |
| A few extreme points (rank statistic) | 100 / 400 | 26% / 67% | A2 / A1 mostly |

For a rank metric, a handful of extreme points moves ranks little, so A1 is weak; at n = 100 most of those tables are just chance passes (109 of 900). Treat
that row as "A1 is a smaller guard than its name suggests", not as a clean measurement. What is solid: **A3 and A4 do their job on measured
columns; they cannot see an unmeasured one**, and the product must say so.

**Not measured:** false-kill with many correlated columns (A3 picks the column most associated with both sides, a search that biases toward finding a
collapse; `min_confound_score` limits it); other claim types and schemes; the joint effect with BH on a family of 8; real tables.

### B4. Severity, pre-registration, nulls: what to do about each

| Topic | Position |
|---|---|
| **Falsifiability / severity** | Give each attack a measured detection rate for its flaw (the table above), kept in the calibration card, and print only K, M, N on a claim. Do not print a "severity score" per claim: it would be an invented number. |
| **Pre-registration / holdout** | The confirmation rows are the holdout and the plan is frozen before they are read. Extend `spec_hash` with the attack-menu ids, thresholds digest and rule version **[OWNER, contract]** so "the attacks were fixed before looking" is true of the proof. Today it is only true of the code path. |
| **Adversarial / placebo / negative control** | Placebo checks need a column known to be unrelated, which only the user knows. Code-only version: re-run the claim's exact test on columns the claim did not name and report how often a random pair does as well (a decoy rank). Config comments already show decoy pairs at 0.28 to 0.30 versus a true 0.33, so the effect floor does not separate truth from chance (`configs/verification.yaml`); only q does. Lipsitch, Tchetgen Tchetgen, Cohen on negative controls: https://pmc.ncbi.nlm.nih.gov/articles/PMC3053408/ . Later, low priority. |
| **Permutation vs parametric nulls** | Permutation is the right choice for a student audience on messy columns, and the add-one p-value (never zero) is the documented right rule (Phipson and Smyth, https://arxiv.org/pdf/1603.05766). Nothing to change. |
| **Specification curve / multiverse** | Simonsohn, Simmons, Nelson, *Specification curve analysis*, Nature Human Behaviour 4: https://www.doi.org/10.1038/s41562-020-0912-z : list all reasonable, non-redundant specifications, display, then joint inference. A1/A3/A5/A4 are four of them. A full curve is over-built for this product; the cheap version is "share of equivalent specifications with the same sign, and the median effect", shown as a descriptive line. Only equivalent ways to ask the same question may count against a claim (Del Giudice and Gangestad, cited in the v3 design doc). |
| **Leave-one-out / subgroup stability** | A4 covers subgroup reversal. Add leave-one-entity-out for CLUSTER and PANEL claims (3 h, full version). |
| **Confounder search** | A3 with up to 1 + 2 controls. A defensible extra: report how strong an unmeasured confounder would have to be to explain the effect away (Rosenbaum and Rubin 1983 style sensitivity analysis, https://search.r-project.org/CRAN/refmans/rms/html/sensuc.html as the software reference found; VanderWeele-Ding E-value, described in https://www.scielo.br/j/csp/a/q679f7RKrxGLCTMCT8rQYGC/?lang=en , a secondary source). Conversions for rank correlations are approximate; later, and only as a descriptive sentence. |
| **Forking paths** | Gelman and Loken: analysis choices contingent on the data are a multiplicity problem even without intent (summary found at https://forrt.org/glossary/english/garden_of_forking_paths/). Relevant to the attacker: every data-dependent choice inside an attack (which column A3 controls, which subgroup column) is a fork. Fixed rules and counting every check in M is the defence. |
| **Replication on held-out rows** | For n at or above a few thousand a third partition ("attack holdout") would give a genuine replication check. Below that it costs power. Not for the first version. Name the check "split-half consistency" and not "replication". |

### B5. How should the failure to break a claim be reported

* Wording: "Held up. Passed the test (q = 0.012, effect 0.31, n = 214). 4 of 5 checks that could be run did not break it; 1 could not tell
  (too few rows in a subgroup). Checked against columns in this table only."
* Never green-wash a low-capacity pass: if fewer than a configured number of checks could be run (say 2), show **Passed, little checked** instead of
  **Held up**. Same verdict (PASS, stored), different label; no change to the memory guard.
* Never report "no attack broke it" without the count M. A claim for which only 1 attack applied is not the same as one that survived 5.

### B6. Where a model may help, where code must decide

| Step | Who | Reason |
|---|---|---|
| Which attacks apply | Code | Applicability is a fact about the table (S3) |
| Attack thresholds, break rule, K, M, label | Code (config) | AGENTS.md 3.3 |
| Computing the attacked effect and its interval | Code | AGENTS.md 3.1 |
| Suggest extra control or grouping columns | DeepSeek, closed menu: only names that exist in the table, capped, validated, fail closed, traced | Already built as S8, off. It can only add checks. |
| Word the result in plain language | Code by default; DeepSeek rewording under the Explainer rules | Existing |
| Write attack code, choose a statistic, drop an attack, argue the claim is true | Nobody | A model that argues for a claim is exactly what the literature search turned up no support for (v3 design doc section 3) |

Honest assessment: code can already rank candidate controls by association (A3's score, the Skeptic's partial associations). The model's only
unique contribution is domain plausibility ("age plausibly drives both"). That is worth a demo line, not a dependency. Keep the refuter off in the first version (reason in B7).

### B7. How to stop the attacker p-hacking in reverse

A larger menu gives more chances to kill true claims; a smaller one lets more false claims survive. The control is a **budget**, not a menu size:

1. **Fix the menu before the data is read** and put its ids, rule version and thresholds digest in the spec hash **[OWNER]**.
2. **Break only on evidence of damage**, at a stated per-claim false-kill budget kappa (suggest 0.10 for n at least 100 and rho at least 0.3): an attack breaks a claim only if
   the confidence interval of its attacked effect (resampling the same unit the null shuffles, as `interval.py` already does) lies wholly below the collapse line or wholly across the sign
   flip, at level 1 - kappa / M. More attacks then make each one harder to trigger, which is the correction for a bigger menu.
3. **Count every check in M**, including model-suggested ones. Extras from the refuter enter M and tighten the others; they are never free.
4. **A third state**, `too noisy to tell`, counts for neither side and lowers the capacity number.
5. **Measure the rates every time anything in the menu changes** (B8), on a card that is part of CI.

### B8. Rates to measure, and how

| Rate | Definition | Design | Target |
|---|---|---|---|
| **False kill (FK)** | P(any attack breaks \| gate PASS, effect is real) | Planted effects, n in {60, 100, 200, 400}, rho in {0.2, 0.3, 0.4}, schemes free / stratified / cluster / block-differenced, 20 extra correlated columns present; 1000 replicates; Wilson interval | At most 0.10 at n at least 100, rho at least 0.3. Today: 0.16 and 0.04 (n = 100 / 200, rho 0.3). |
| **False survive, mechanism (FS-m)** | P(HELD UP \| gate PASS, planted flaw f) for f in {measured confounder, Simpson, late-period-only, extreme points, identity/leakage, entity-driven, **unmeasured confounder**} | Planted-flaw generators next to the existing planted cases in `test_attacks.py` | At least 0.9 detection for the measured ones; **0 for unmeasured, stated as a limit**, not tuned |
| **False survive, chance (FS-c)** | P(HELD UP \| gate PASS, no effect) | Pure null, family of 8, BH on | Reported, not targeted. Today 0.71 to 0.77 of single luck-passes survive. The end-to-end rate (BH alpha times this) is the number to quote. |
| **Capacity** | Share of PASS claims where fewer than 2 checks could be run | Real tables | Report; decides the "little checked" label |
| **End to end** | P(any false HELD UP in a run of 8) with BH + attacks | Family scenarios of A6, plus attacks | Report next to BH-only; shows the attacks' real contribution |

---

## C. Proposed design: the refutation gate

### C1. Flow (text diagram)

```
claims (structured, from exploration rows)              -- unchanged
  |
  1 SPEC    freeze: claim, test, scheme, seed, split digest,
  |         attack menu ids + rule version + thresholds digest   -> spec_hash v2   [OWNER, contract]
  2 ADMIT   admissibility + NOT_TESTABLE                     -- unchanged
  3 TEST    permutation p per claim; BH ONCE per run          -- unchanged   (REJECT is final)
  |         -> SUPPORTED (PASS candidate) | REJECT
  4 ATTACK  only SUPPORTED; applicable attacks of the fixed menu; CODE ONLY
  |           for each attack a: attacked effect e_a, interval [lo_a, hi_a]  (same resampling unit as the null)
  |           BROKEN        interval wholly below collapse line / across the sign flip, at 1 - kappa/M
  |           SURVIVED      interval reaches the collapse line
  |           TOO_NOISY     interval spans both          (neither side)
  |           NOT_APPLICABLE / NOT_RUN                   (neither side)
  |         [optional, off] DeepSeek adds up to 2 control / 2 group NAMES; validated; counted in M
  5 LABEL   any BROKEN                         -> REJECT / FRAGILE (not stored)
  |         PASS, capacity >= c_min (2)        -> HELD UP    "K of M survived, N too noisy"
  |         PASS, capacity <  c_min            -> PASSED, LITTLE CHECKED   (still PASS, still stored)
  6 LEDGER  look count (existing) + M recorded
  7 EXPLAIN code sentence from the proof; the existing Explainer rules for any model wording
```

Code decides: steps 1 to 6. Model: only the optional name suggestion in step 4 and optional rewording in 7. Nothing a model writes is evidence.
Invariants kept and tested: REJECT never upgraded; FRAGILE never stored; `memory_write => verdict == PASS` and `gate_outcome == SUPPORTED`
(`memory_guard.py`); the ratchet only lowers.

### C2. Changes to the proof (`ProofObject`, `AttackResult`)

| Change | Needed for | Contract change? |
|---|---|---|
| `AttackResult.details` gets `attacked_low`, `attacked_high`, `kappa`, `n_checks` | interval rule | No (`details` already holds floats) |
| `AttackOutcome` gains `TOO_NOISY` | third state | **Yes** [OWNER] (enum). First version avoids it: `NOT_RUN` with `applicable=True` and `details.too_noisy = true`. |
| `ProofObject.robustness` (`held_up` / `little_checked` / null) | label | Optional field with default; old proofs load [OWNER, 8.7]. Derivable from `attacks`, so first version computes it in the API layer with no contract change. |
| `spec_hash` v2 covers menu, rule version, thresholds digest | pre-registration claim | **Yes** [OWNER]; `spec.matches` must accept v1 for old proofs |

### C3. Files

`src/pramana/verification/attacks/runner.py` (break rule), `verification/config.py` and `configs/verification.yaml`
(`attacks.break_rule: point | interval`, `attacks.false_kill_budget`, `attacks.min_capacity`; thresholds stay in the one config file, AGENTS.md 3.3),
`verification/interval.py` (reuse the resampler), `verification/gateway.py::_attacked` (counts), `verification/spec.py` (v2), `contracts/attack.py`,
`contracts/proof_object.py` (optional), `scripts/calibration/gate_report_card.py` (A6 and B8 rows), `tests/unit/verification/test_attacks.py`,
`tests/unit/verification/test_gate_report_card.py`, API/web text for the label.

### C4. Effort

| Version | Hours | Contents |
|---|---|---|
| **First (fits one working day, thesis-review demo)** | **about 7.5** | Report card: correlated family of 8 with none / BH / Holm and attack FK / FS rows (3.5 h). Label text "K of M survived, N could not tell, measured columns only" from existing attacks (1 h). `break_rule: interval` for A2 and A4 only, behind a flag **default `point`** (2.5 h). Written results in this doc (0.5 h). |
| **Full** | **about 40** | Interval rule for all attacks with Bonferroni across M (6 h); leave-one-entity-out (3 h); multi-control A3 (4 h); sensitivity sentence for unmeasured confounding (5 h); spec hash v2 + `TOO_NOISY` + `robustness` contract changes (3 h + owner review); planted-flaw library (6 h); FK / FS on NHANES and the retail table (5 h); third partition for large n (6 h, split change); tests and docs (4 h). Chat / dataset ledger with online FDR stays parked. |

Approvals: every row that changes the break rule, the contracts, the split, or the family correction is **[OWNER]**. Report-card scenarios and
label text for existing outcomes are not.

---

## D. Risks and what not to do (ranked) and five questions

### D1. Risks

1. **Overclaiming "held up".** Printed without K, M, N and "measured columns only" it reads as "verified". Biggest thesis-review risk; free to fix.
2. **The attack stage discards real findings at student-sized n** (measured above), then the tool says "fragile" about a true claim. It also contradicts the
   owner's own principle: killing needs proof.
3. **Believing the attacks protect against false positives.** They remove about a quarter of luck-passes. Do not loosen BH or the effect floor because "the attacks will catch it".
4. **Loosening the ratchet without the false-survive numbers.** Switching A2/A4 to intervals lowers kills and lets more claims reach memory; that moves toward the
   prime directive. Ship it flag-off, flip only with FS-m and FS-c on the card.
5. **Uncorrected multiplicity across chat and reruns** (A7). Disclose now, fix later.
6. **Menu inflation.** Turning the refuter on, or adding A8 to A12, adds false kills and breaks the "menu fixed in advance" story. Count extras in M or do not add them.
7. **Letting a model near thresholds, the break rule, or an attack's code.** Breaks AGENTS.md 2 and 3.
8. **Calling `spec_hash` pre-registration.** It is tamper evidence over a subset of the plan.
9. **Building heavy FDR machinery first** (Westfall-Young, e-BH, BY, full online FDR). Measured evidence does not ask for it.
10. **Editing thresholds before the review to make the demo look better.** The v3 design already forbids it.

### D2. Do not

* Do not drop BH, switch to BY, or build Westfall-Young now.
* Do not add attacks or turn the refuter on for the review.
* Do not change `shrink_fraction` to hide the A2 problem; fix the rule, not the number.
* Do not give any model a path to a number, a break decision, or a verdict.
* Do not claim a false-kill or false-survive rate in the report without the card behind it (n, replicates, SE).

### D3. Five questions for the owner, first

1. **What is the promise?** "On average few false cards" (FDR, keep BH) or "no false card in a run" (FWER, Holm)? Who reads a card without its caveats?
2. **Is a FRAGILE claim shown or hidden, and what false-kill budget is acceptable?** I suggest at most 0.10 at n at least 100 and rho at least 0.3. Today a true rho 0.3 at n = 100 is killed 16% of the time.
3. **Chat:** is a raw p-value with disclosure acceptable for the review, or must each chat claim carry a cumulative budget now?
4. **Reruns:** do users run the planner several times on one dataset? If yes, a dataset-level correction or at least a cumulative-risk line is required; if no, document the assumption.
5. **May the break rule change and spec hash v2 (contract) be approved before 27 Oct,** or should the review show the card and the measured problem and leave the change for after? AGENTS.md 8.10 needs your approval either way.

---

## E. What to improve, in order (added at the request of another session working for the owner)

### E1. About one working day, ranked by value to a thesis review

| # | Item | Hours | Files | Risk to `memory_write => verdict == PASS` | Needs owner (8.10) |
|---|---|---|---|---|---|
| 1 | **Report card: correlated family of 8 (none / BH / Holm), plus attack false-kill / false-survive rows.** Turns A and B from argument into numbers; the scenarios exist as prototypes in the appendix. | 3.5 | `scripts/calibration/gate_report_card.py`, `tests/unit/verification/test_gate_report_card.py` | None: measurement, no verdict touched | Thresholds only; no for scenarios |
| 2 | **Label: "K of M checks survived, N could not tell, measured columns only"; "little checked" when fewer than 2 ran.** Fixes the biggest overclaiming risk (D1.1). | 1.0 | API/web text; `gateway.py` counts if needed | None: same verdicts, same memory rule | Wording already approved (v3 decision 5); the "little checked" label is new, tell the owner |
| 3 | **`break_rule: interval` for A2 and A4 behind a flag, default `point`.** Present the measured false-kill problem and a working fix. | 2.5 | `attacks/runner.py`, `verification/config.py`, `configs/verification.yaml`, `test_attacks.py` | None while the flag is off. Flipping it **loosens** the ratchet, so it requires item 1's FS rows first | **Yes** (statistics, attack rule, config keys) |
| 4 | **Fix the wording around `spec_hash`** so no document claims pre-registration of the attack plan. | 0.5 | `docs/` only | None | No |
| 5 | **Chat cumulative-risk line** ("claim k of 50; if everything asked so far were unrelated, chance of at least one false PASS by now is X%"). | 1.5 | `chat/service.py` text, web text | None: disclosure only, no verdict | Wording of a statistical disclosure: tell the owner (AGENTS.md 2 sentence on chat) |

Items 1 to 4 are about 7.5 h, one day. Item 5 is the overflow. Do items in this order: nothing in 3 or 5 should be argued without 1.

### E2. Later

* Interval rule for every attack with Bonferroni across M, a `TOO_NOISY` state, `robustness` field, spec hash v2 (contract changes) **[OWNER]**.
* Leave-one-entity-out and multi-control A3; planted-flaw library for FS-m; FK / FS on NHANES and the retail table.
* Third partition for large n (genuine replication) **[OWNER, split]**.
* Dataset-level online FDR for chat and reruns (alpha-investing / LORD++ / SAFFRON), with the independence assumption written next to the code **[OWNER]**. Revisit only if chat becomes a long-session feature.
* Unmeasured-confounder sensitivity sentence; decoy-rank negative control.
* Switch to Holm only if the owner answers "FWER" in D3.1 or the extended card shows BH FDR above 0.065.

### E3. What my findings make unnecessary (do not build)

| Item | Why my findings argue against it |
|---|---|
| G10 / S10 Westfall-Young or joint permutation across claims | Five different null schemes: no single joint shuffle. BH showed no excess in the structure measured. Build only if the A6 card fails. |
| e-BH / e-values | Permutation p-values are not e-values; no evidence of an FDR failure to repair. |
| BY as the default | Costs roughly 10% to 70% of power at m of 8 to 24 for a problem not seen. |
| More attacks (A8 and up), or the refuter on by default | Menu inflation: more false kills. The attacks catch mechanisms, not luck, so more of them do not buy more protection against false positives. |
| Raising or lowering `shrink_fraction` | Treats a rule defect (point estimate, no allowance for noise) as a threshold defect. |
| A model that "argues" a claim holds | No support found; breaks the invariant that a model never defends. |
| Thresholdout-style noisy holdout or fresh random split on a new seed | Time-ordered splits cannot be redrawn (S7 note); the real exposure is cross-run multiplicity, which a ledger-based correction or disclosure handles. |
| Data fission / thinning | Parametric assumptions that clustered and dependent data break (v3 design doc); no measured need. |
| Dropping the effect floors, or relying on attacks instead of the effect floor | Floors do not separate truth from chance (config comment) but they stop trivial large-n effects, which attacks do not. Different job. |
| Online FDR for chat right now | Parked by decision; the cumulative-risk line (item 5) is enough for a demo. |

### E4. The single first step

**Do E1 item 1: extend the report card with the correlated family of 8 and the attack FK / FS rows.** Reasons: (a) both of your questions are answered by numbers it would
produce, not by opinion; (b) it changes no verdict and cannot touch the prime directive; (c) every later decision (keep BH, Holm, interval rule, what kappa to use) is a
read-off from it; (d) the prototype already exists, so this is porting, not research, and the result is a thesis figure.

---

## Limits of this note

* My two simulations use planted synthetic tables I wrote, small replicate counts, one dependence structure for BH, one claim type and scheme for the attacks, and the
  gate was approximated by a Spearman test (BH run) or a Spearman p-value plus the effect floor (attack run), not the full gateway. The numbers show where to look; the
  report card is where they become evidence.
* Literature was read through search summaries and abstracts. Where a claim matters for a decision, it is marked. The Dobriban preprint was not read.
* I did not run the repo's full test suite (documentation-only change) and did not change any source file.

---

## Appendix: the two prototype scripts (not in the repo tree; reproduce with `PYTHONPATH=src:.`)

`atk_sim.py` uses the repo's `run_attacks` and `tests.fixtures.config.load_pinned_config`. `bh_sim2.py` needs only numpy, scipy and statsmodels.

### `bh_sim2.py` (BH, BY, Holm, Bonferroni under shared columns)

```python
import numpy as np
from scipy.stats import rankdata
from statsmodels.stats.multitest import multipletests
rng=np.random.default_rng(7); B=999
def perm_p(X,Y):
    n,m=X.shape
    c=lambda A:(A-A.mean(0))/np.linalg.norm(A-A.mean(0),axis=0)
    Xc,Yc=c(X),c(Y); obs=np.abs((Xc*Yc).sum(0)); cnt=np.zeros(m)
    for _ in range(B):
        cnt+=np.abs((Xc*Yc[rng.permutation(n)]).sum(0))>=obs-1e-12
    return (1+cnt)/(B+1)
def make(n,k_true,beta,n_null_cols=5,fcorr=0.6):
    H=rng.normal(size=n)
    T=[beta*H+rng.normal(size=n) for _ in range(3)]          # T_i correlated with H and (weakly) each other
    F=rng.normal(size=n)
    N=[np.sqrt(fcorr)*F+np.sqrt(1-fcorr)*rng.normal(size=n) for _ in range(n_null_cols)]  # mutually correlated, independent of H,T
    cols={'H':H,**{f'T{i}':T[i] for i in range(3)},**{f'N{i}':N[i] for i in range(n_null_cols)}}
    return cols
def pairs_for(mode,k_true):
    tr=[('H',f'T{i}') for i in range(k_true)]
    if mode=='m8':
        nu=[('H','N0'),('H','N1'),('H','N2'),('T0','N0'),('T1','N1'),('T2','N2'),('H','N3'),('T0','N3')]
        nu=nu[:8-k_true]
    else: # m24: all H/T x N pairs
        nu=[(a,f'N{j}') for a in ['H','T0','T1','T2'] for j in range(5)]
        nu=nu[:24-k_true]
    # when k_true<3, T_i for i>=k_true are independent of H, but T_i used only in null pairs -> still null (beta=0 for them)
    return tr+nu,len(tr)
def run(mode,n,k_true,beta,reps=300):
    pairs,kt=pairs_for(mode,k_true)
    out={k:[0.,0.,0.] for k in ['raw','BH','BY','Holm','Bonf']}; nl=len(pairs)-kt
    for _ in range(reps):
        cols=make(n,k_true,beta)
        # T_i for i>=k_true must be null w.r.t H
        for i in range(k_true,3): cols[f'T{i}']=rng.normal(size=n)
        R={k:rankdata(v) for k,v in cols.items()}
        X=np.column_stack([R[a] for a,b in pairs]);Y=np.column_stack([R[b] for a,b in pairs])
        p=perm_p(X,Y); truth=np.arange(len(pairs))<kt
        for key,meth in [('raw',None),('BH','fdr_bh'),('BY','fdr_by'),('Holm','holm'),('Bonf','bonferroni')]:
            rej=p<0.05 if meth is None else multipletests(p,0.05,method=meth)[0]
            nr=rej.sum();fp=(rej&~truth).sum()
            out[key][0]+=fp/nr if nr else 0; out[key][1]+=fp>0; out[key][2]+=(rej&truth).sum()/max(kt,1)
    print(f"{mode} n={n} true={kt} null={nl} beta={beta} (rho~{beta/np.sqrt(1+beta**2):.2f}) reps={reps}")
    for k,v in out.items(): print(f"   {k:5s} FDR={v[0]/reps:.3f}  P(any false)={v[1]/reps:.3f}  power={v[2]/reps:.3f}")
run('m8',100,0,0.3); run('m8',100,3,0.3); run('m8',100,3,0.45); run('m8',60,3,0.45)
run('m24',100,3,0.3); run('m24',100,3,0.45); run('m24',100,0,0.3)
```

### `atk_sim.py` (attack false-kill and false-survive, run from the repo root)

```python
import zlib
import numpy as np, pandas as pd, sys
from scipy.stats import spearmanr
from collections import Counter
from pramana.contracts.attack import AttackOutcome
from pramana.contracts.enums import ClaimType, PermutationScheme
from pramana.verification.attacks import ClaimView, run_attacks
from pramana.verification.attacks.runner import PERIOD_COLUMN
from tests.fixtures.config import load_pinned_config
cfg=load_pinned_config().attacks
claim=ClaimView(ClaimType.CORRELATION,"x","y",PermutationScheme.FREE)
def gate_pass(f):
    r,p=spearmanr(f.x,f.y); return p<0.05 and abs(r)>=0.10
def table(rng,n,kind,rho):
    site=rng.choice(list("abc"),size=n); noise=rng.normal(size=n)
    if kind=="true":
        x=rng.normal(size=n); y=rho*x+np.sqrt(1-rho**2)*rng.normal(size=n)
    elif kind=="confounded":   # x,y both driven by observed z, no direct link
        z=rng.normal(size=n); x=0.8*z+0.6*rng.normal(size=n); y=0.8*z+0.6*rng.normal(size=n); noise=z
        return pd.DataFrame({"x":x,"y":y,"z":z,"site":site})
    elif kind=="simpson":     # within each site negative, between sites positive
        s=pd.Series(site).map({"a":0,"b":3,"c":6}).to_numpy(float)
        x=s+rng.normal(size=n); y=s*1.2-0.6*(x-s)+rng.normal(size=n)*0.5
        return pd.DataFrame({"x":x,"y":y,"z":noise,"site":site})
    elif kind=="outliers":    # 4 extreme points manufacture the link
        x=rng.normal(size=n); y=rng.normal(size=n); k=max(3,n//40)
        x[:k]=np.linspace(8,12,k); y[:k]=np.linspace(8,12,k)
        return pd.DataFrame({"x":x,"y":y,"z":noise,"site":site})
    return pd.DataFrame({"x":x,"y":y,"z":noise,"site":site})
def cell(kind,n,rho,reps):
    rng=np.random.default_rng(zlib.crc32(f"{kind}-{n}-{rho}".encode()))
    passed=killed=0; by=Counter(); applic=[]
    for i in range(reps*6):
        f=table(rng,n,kind,rho)
        if not gate_pass(f): continue
        f[PERIOD_COLUMN]=0.0 if False else np.arange(len(f))*0.0
        f=f.drop(columns=[PERIOD_COLUMN])
        res=run_attacks(claim,f,cfg,seed=i)
        passed+=1; br=[r.attack_id for r in res if r.outcome is AttackOutcome.BROKEN]
        killed+=bool(br); by.update(br)
        applic.append(sum(r.outcome is AttackOutcome.SURVIVED for r in res))
        if passed>=reps: break
    print(f"{kind:10s} n={n:4d} rho={rho:.2f} gate-passed={passed:3d} killed={killed/passed:.2f} by={dict(by)} mean_survived_checks={np.mean(applic):.1f}",flush=True)
for n in (60,100,200,400):
    for rho in (0.0,0.2,0.3,0.4): cell("true",n,rho,150)
for n in (100,400): 
    for k in ("confounded","simpson","outliers"): cell(k,n,0,150)
```

Note: `atk_sim.py` keeps tables whose Spearman p is below 0.05 and |rho| at least 0.10 as a stand-in for the gate; its first line was added to seed each cell with `zlib.crc32` so the run is reproducible. Output of the final run: `atk_final.txt` summarised in section B3.
