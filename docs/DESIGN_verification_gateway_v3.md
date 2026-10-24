# Verification gateway v3: design proposal

Status: PROPOSAL for the verification owner (P.P. Satya Karthikeya). Nothing here is
built. Every change to p-values, FDR, the split, or sandbox safety needs sign-off
under AGENTS.md §8.10. Written 2026-10-24 against branch `feat/satya/findings-ui`
(PR 29).

## 1. The one idea

A claim reaches the user only if it has survived an honest attempt to break it, and
the attempt is made by code we can audit. Three rules follow.

1. **The gate is the evidence.** The permutation test, one BH correction per run and
   the effect band decide whether a claim is more than chance. Nothing downstream can
   turn a REJECT into a PASS.
2. **An agent may attack, never defend.** A model may pick which attacks fit a claim
   and explain the outcome in plain words. It never decides, never computes a number,
   and never argues that a claim is true.
3. **"Not disproved" is not "correct".** The strongest label we can give is *held up*:
   it passed the gate, and these N checks failed to break it. Words like "proven",
   "correct" or "true" never appear.

## 2. What is weak today (honest list)

Each item is something I believe is true from the code and the live runs, with how
sure I am.

| # | Weakness | Why it matters | Sure? |
|---|---|---|---|
| W1 | One 50/50 split, used once per run, but the same confirmation rows are reused by every later run and every chat question on that dataset | Looking at the held-back rows many times, adaptively, slowly turns them into training data. The reuse leak is the known failure of a plain holdout | High (by construction); size of leak unmeasured |
| W2 | Half the rows are lost to exploration | Lower power; true, smaller effects are rejected. This is the "true claim rejected" complaint | High |
| W3 | BH assumes independent or positively dependent p-values; claims in one run share columns | FDR may be above alpha in a dense run | Medium: no measurement on real tables |
| W4 | DeepSeek writes the `falsify(frame)` program, so it chooses the test | A model that picks the test is a place for forking-paths choices. The library supplies the p-value, but the choice of test is still the model's | Medium |
| W5 | Attack thresholds are PROVISIONAL, tuned on planted cases, false-kill measured only on simulations | An attack could kill real claims on real, messy data | High |
| W6 | All seven attacks run for every claim, even where they do not apply | A check that does not fit the claim should not count against it | Medium |
| W7 | The effect band uses the point estimate | A band decision on a noisy estimate flips easily; no interval is shown | High |
| W8 | A REJECT looks like "false" in the UI | It means "not enough evidence at this size" | High |
| W9 | Chat claims sit outside the BH family; the question is open (AGENTS.md §2) | Many chat questions on one table is a multiple-testing problem with no budget | High |
| W10 | No standing calibration of the whole gate | Planted-null and planted-effect tests exist per scheme, but there is no one report card for false-positive rate and power | Medium |

## 3. What the literature offers (and what it does not)

Found by search on 2026-10-24. I read search summaries, not the full papers, so each
claim below should be checked before it goes in a report or a code comment.

- **Reusable holdout (Dwork, Feldman, Hardt, Pitassi, Reingold, Roth, 2015).**
  The holdout is reached only through a mechanism that adds noise and counts how
  often it is used, so many adaptive analyses can be validated without overfitting the
  holdout. Fits W1. The full Thresholdout mechanism is not needed; the idea we take
  is a **per-dataset budget of looks at the confirmation rows**.
  [arXiv 1506.02629](https://arxiv.org/pdf/1506.02629.pdf)
- **E-values and e-BH (Wang and Ramdas).** BH applied to e-values controls FDR under
  arbitrary dependence, with no log-K penalty as in BY. Fits W3, but needs e-values,
  not permutation p-values. A real research track, not a quick change.
  [arXiv 2009.02824](https://ar5iv.labs.arxiv.org/html/2009.02824),
  [stopped e-BH, arXiv 2502.08539](https://arxiv.org/pdf/2502.08539)
- **Online FDR: alpha-investing, LORD, SAFFRON (Ramdas et al., 2018 and later).**
  Tests arrive one at a time; each threshold depends only on the past; FDR is
  controlled at every moment. This is exactly the chat situation (W9). Guarantees need
  independence or a "local" non-negative dependence condition, so the assumption must
  be stated.
  [SAFFRON, arXiv 1802.09098](https://arxiv.org/pdf/1802.09098),
  [dependence results, arXiv 2110.08161](https://arxiv.org/abs/2110.08161v2)
- **Data fission and thinning (Leiner et al. 2023; Neufeld et al. 2024).** Split one
  observation into two independent parts by randomization, instead of splitting rows.
  Could recover power (W2) but needs parametric assumptions that clustered or
  dependent data break. Not for now.
  [arXiv 2112.11079](https://arxiv.org/pdf/2112.11079)
- **Multiverse and specification-curve analysis.** Run all defensible analysis
  choices and show the spread. Del Giudice and Gangestad warn that mixing in
  non-equivalent, poorly justified alternatives can hide a real effect. This is the
  argument for W6: only attacks that are *equivalent* ways to ask the same question
  may count against a claim.
  [Del Giudice and Gangestad 2021](https://arts.units.it/retrieve/514d5b20-e3e5-4c08-af56-0a95170bfcb1/del-giudice-gangestad-2021-a-traveler-s-guide-to-the-multiverse-promises-pitfalls-and-a-framework-for-the-evaluation-of.pdf)
- **Model-chosen tests and p-hacking.** Fisher-R1 and P-Bench (preprint, author
  reported) argue that checking whether an agent's p-value is *valid for the data's
  assumptions* is rarely tested. A separate study, seen only via a summary, reports
  that models refuse explicit requests to p-hack but drift under "explore
  alternatives" framing. Both support W4: do not let a model choose the test.
  [arXiv 2608.07437](https://arxiv.org/pdf/2608.07437)

Not found: any paper that supports "an LLM that argues why a claim is true" as a
verification step. I would not build that.

## 4. The v3 design

```
claim (structured, from planner/chat)
  1. SPEC      freeze the spec: claim, test, scheme, split seed, attack list -> hash
  2. ADMIT     admissibility + NOT_TESTABLE refusals (as today)
  3. GATE      scheme-matched permutation test on confirmation rows
               + interval on the effect + one correction per run
               -> PASS | REJECT | NOT_TESTABLE
  4. ATTACK    only on PASS: applicable attacks only, code-run, consistency-judged
               -> HELD_UP | FRAGILE (and which attack, in words)
  5. LEDGER    every look at the confirmation rows is counted per dataset
  6. EXPLAIN   code writes the sentence; an optional model rewords it under the
               explainer rules; nothing it writes is evidence
```

### G1. Spec before reveal (commit, then look)
Before any confirmation row is read, hash the full spec (claim, variables, test id,
scheme, seed, split seed, attack list, thresholds version) and stamp it on the proof.
The executor refuses a result whose spec hash differs. This makes "I changed the test
after seeing the data" impossible to hide. Small, mostly bookkeeping.

### G2. Test registry replaces model-written tests for standard claims
For each existing claim type there is already one vetted function in
`pramana.verification.stats`. The gate picks it by claim type and scheme; no
generated program is needed. Keep model-written `falsify(frame)` only for claim types
without a registry entry, and mark those proofs "model-written test".
**Owner decision**: AGENTS.md §2 currently names writing `falsify(frame)` as the model's
role in the gateway. This changes that role, so it needs explicit sign-off. It removes
W4 and a whole class of sandbox risk, and makes the gate faster and reproducible.

### G3. Interval on the effect; band on the lower bound
Report a confidence interval from a bootstrap (block bootstrap for ordered data) next
to the point estimate. PASS needs q below alpha and the **lower end of the interval**
above the band floor, or the rule is changed to point estimate plus interval shown.
Which of those two is a statistics decision; I recommend showing the interval first,
changing the rule only after G9 shows what it does to power.

### G4. Dataset look budget (reusable-holdout idea)
A per-dataset counter of looks at the confirmation rows, shown in the UI. When it
passes a configured limit, a fresh split is created on a *new random seed* and old
claims are marked "from an earlier split". The limit is a config value. This does not
claim to be Thresholdout; it is a cheap guard that makes W1 visible and bounded.

### G5. Applicable attacks only
Each attack declares when it applies (needs a time column, a grouping column, a third
numeric column, and so on) in code. Not-applicable is `not_run: not_applicable` and
never counts for or against. The agent in G7 may *rank* the applicable attacks and
explain, but applicability itself is code.

### G6. Wording and verdict states
- `PASS` -> shown as "held up" with "survived N of M applicable checks".
- `FRAGILE` -> "passed the significance test, but did not hold under <check>". Still
  never written to memory (`memory_write => verdict == PASS` unchanged).
- `REJECT` -> "not enough evidence at this sample size", with n and effect size.
- A **power note** on every REJECT: the smallest effect the confirmation rows could
  have detected at the run's alpha (analytic or by simulation, config-bounded).

### G7. Refuter agent (the idea from this chat)
DeepSeek, fail-closed without Langfuse, traced under the run id. Input: claim spec
and a column profile (names, types, roles), never rows. Output: a closed JSON list of
attack ids from the menu with a one-line reason each, plus after the run a
plain-language explanation of the results. Code validates every id, drops anything off
the menu, runs the checks, decides. The agent has no path to a number, a verdict or
memory. It tries to break the claim; it never argues for it. If it fails, the full
applicable menu runs and the failure is recorded (no silent substitution, AGENTS.md §2).

### G8. Online FDR for chat claims
Give each dataset an alpha-wealth budget (alpha-investing or LORD, or SAFFRON if the
claims can be treated as independent). Each chat claim is tested at a threshold set by
remaining wealth; discoveries earn some back. This replaces the open question of
"should chat claims join a BH family" with a defined procedure. **Owner decision**, and
the independence assumption must be written next to the code.

### G9. Gate report card (calibration, small)
One reproducible script and one CI test that prints, per scheme and claim type: false
positive rate on planted nulls (target at most alpha), power on planted effects at
several sizes and n, false-kill rate of the attack set on true effects, and the share
of runs where BH level is exceeded on correlated claim families (W3). Fixed seeds. This
is not the parked P0 evaluation; it is the gate's own acceptance test, and every other
step is judged by it.

### G10. Dependence across claims in a run (W3)
First measure with G9. If FDR is above alpha on correlated families, switch the
within-run correction to a permutation-based joint procedure (Westfall-Young style max
statistics reuse the same shuffles, so dependence is respected) or to BY as a
conservative fallback. E-BH only if G9 shows it is needed and an e-value construction
is agreed.

## 5. Order of work and what each step must prove

| Step | Change | Done when | Needs owner |
|---|---|---|---|
| S1 | G6 wording + power note | UI/API text reviewed; no verdict logic changed; tests pass | no |
| S2 | G9 report card | script + test run green; numbers recorded in this doc | thresholds only |
| S3 | G5 applicability | each attack has a coverage test for applies / not applies | no |
| S4 | G1 spec hash | executor refuses a changed spec; proof carries hash | yes (proof contract) |
| S5 | G3 interval | interval on proof; band rule unchanged | yes |
| S6 | G2 registry | every claim type has a registry test; parity test vs generated code | yes (§2 role) |
| S7 | G4 look budget | ledger + fresh-split path; tests | yes (split) |
| S8 | G7 agent | closed-menu validation tests; fail-closed tests; Langfuse trace | yes (§2 role) |
| S9 | G8 online FDR | PARKED (decision 4) | yes (statistics) |
| S10 | G10 | only if S2 shows a problem | yes |

Rule for every step: the invariant `memory_write => verdict == PASS` and "REJECT can
never be upgraded" must have a test that fails if broken. A step that cannot show that
is not done.

## 6. What we will not do

- No model decides, computes, or argues that a claim is true.
- No second chance: surviving attacks never rescues a gate REJECT.
- No threshold edited to make a demo pass; thresholds change only through
  `configs/verification.yaml` and G9 numbers.
- No raw rows to any model.

## 7. Decisions (verification owner, in chat, 2026-10-24)

The owner accepted the recommendation on each question. Recorded here so the build
steps can cite them; the PR for each step still needs the owner's review (§8.10).

1. G2 test registry: **approved in direction.** Vetted tests are chosen by claim type;
   model-written tests only for claim types with no registry entry. AGENTS.md §2 must
   be amended in the same PR as S6.
2. G3 interval: **show the interval only.** The band rule does not change until the
   report card (S2) shows its effect on power.
3. G4 look budget: **approved**; the limit is set from the report card, not guessed.
4. G8 online FDR for chat claims: **PARKED.** Chat is for testing in this phase, not
   long sessions. S9 is not built now; the chat ledger stays as it is.
5. G6 wording ("held up", "did not hold under X", "not enough evidence"): **approved.**
6. Demo first: no step may break the demo flow (section 9).

## 8. Original open questions (kept for the record)

1. G2: may the gate use a registry of vetted tests instead of model-written programs
   for standard claim types?
2. G3: interval shown only, or also used in the band rule?
3. G4: what look limit per dataset before a fresh split (suggest a small number, to
   be set from G9)?
4. G8: alpha-investing or LORD, and is treating chat claims as independent acceptable?
5. FRAGILE wording: "held up" and "did not hold under X" as above?

## 9. Demo check (done 2026-10-24)

Dataset `data/demo/nhanes_demo.csv` on the live preview API with the planner engine and
real DeepSeek: completed in about 4.7 minutes; 3 PASS, 2 REJECT (1 negligible, 1
fragile), 0 unverified; split `random_rows`; 7 attacks on each claim that reached
them; 4 planned Measured items; every claim has a proof. This was before S1-S10, so it
is the baseline. Every step must repeat this check and not make it worse.

## 10. Limits of this document

Literature notes come from search summaries and have not been read in full. The size
of the W1 and W3 problems is not measured; G9 exists to measure them. I have not
checked how the 50/50 split behaves at very small n beyond the existing tests.

## 11. Financial-year check (2026-10-24, synthetic data with planted effects)

Table: 36 months (Apr 2022 to Mar 2025) x 4 regions x 3 products = 432 rows. Planted:
South grows fastest, Oct-Dec is high and Jun-Jul low, the Lite product's cost ratio
climbs, one revenue row is multiplied by 6. Real DeepSeek, planner engine. The data is
synthetic, so this shows what the platform does with each planted fact, not how it
does on real books.

Found by the Exact tier (good): revenue +11.5% year on year; South is 73.8% of the
rise; December is 1.34x an average month, June 0.78x.

Gaps (each is a work item):

| # | Gap | Evidence | Fix |
|---|---|---|---|
| F1 | Run ends "degraded": 2 of 7 claims lost | Model-written tests for the two group claims were refused by the column policy ("indexed by a slice, mask or expression the claim does not state") | S6 registry of vetted tests; priority up |
| F2 | Trend claim NOT_TESTABLE | 36 months split 50/50 leaves 18 in the confirmation rows; the minimum is 20 | Owner decision: claims fixed before looking at the data (the standard checklist) could be tested on all rows, since nothing was chosen from them |
| F3 | Tested claims are weak | "latest month lower than the month before"; revenue vs units; revenue vs marketing spend | Steer the planner to year-on-year change, seasonality and segment-drove-change (T5) |
| F4 | No margin or ratio | Cost +16.2% against revenue +11.5% is never stated | Build E7 ratios and margins |
| F5 | Planted 6x revenue row not listed | Outliers checked on month totals only; the isolation forest flags 9 rows | Row-level robust outliers in the Exact tier |
| F6 | No fiscal-year wording | Shown as "12 months to 2025-03"; no FY labels or fiscal quarters | Fiscal-year start in config or detected from a fiscal column |
| F7 | Measured models not run on transaction tables | "Rows share periods, so they cannot be held out in time order" | Aggregate to period x segment, then model |
