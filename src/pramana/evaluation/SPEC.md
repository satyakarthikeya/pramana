# Evaluation spec — ground truth and the four conditions

> Owner: P.P. Satya Karthikeya
> Status: SPEC ONLY. Write this down before building the harness, because the harness
> is worthless if the scoring rule is decided after seeing the outputs.
> Context: `PROJECT.md` §6, `docs/OPEN_ISSUES.md` issues 2 and 3.

## 1. The problem this solves

The ablation compares four systems on 40 datasets and claims D reports more correct
insights than A, B and C. "Correct" needs a definition that exists **before** any
system runs, or the comparison is unscoreable — and a definition that cannot be
argued with afterwards, or it is unpublishable.

Two candidate sources of truth, and why only one is the primary:

| Source | Problem |
|---|---|
| Published findings on NHANES / NFHS-5 | Sparse, contested, defined on different subsets and covariate adjustments than ours. It tells us a relationship exists *somewhere in the literature*, not that it holds in our extract. And it gives no negatives at all — we would know some true relationships and nothing about which pairs are null, so **recall is computable and precision is not**. |
| Planted, by construction | Exact, complete, reproducible. Every pair is labelled: the injected ones are true, every other pair is a true null. Costs realism. |

**Decision: planted is primary. Published is a demo garnish, not evidence.**

## 2. How a benchmark dataset is built

Per dataset, from a logged seed:

1. Take a real NHANES / NFHS-5 extract. Keep the real column names, dtypes, missingness
   pattern and marginal distributions — this is what makes the benchmark look like real
   data rather than a simulation.
2. **Independently shuffle every column.** This destroys every real association while
   leaving each marginal exactly as it was. The frame is now, by construction, pure
   null: any association a system reports at this stage is a false positive, and we
   know it without argument.
3. **Inject `k` relationships** with known type, effect size and direction — a monotonic
   association on a numeric pair, a location shift between levels of a categorical, a
   trend against a time column. `k` and the effect sizes are drawn from a logged
   schedule, not chosen per dataset by hand.
4. Record the ground-truth table: every injected pair with its type, magnitude and
   direction; every other pair marked null.

The shuffle in step 2 is the load-bearing step. Without it the extract still carries
its real correlations, those would be unlabelled, and a system reporting one would be
scored as wrong when it was right.

### Effect sizes to inject

Span the gate's decision boundary deliberately: some clearly above the configured
`min_effect`, some just above, some in the NEGLIGIBLE band just below. A benchmark
where every planted effect is huge measures nothing except whether the code runs.

## 3. Scoring

Both precision and recall are exact, because the label set is complete.

- **Precision** — of the insights a system reports, the fraction that correspond to an
  injected relationship *with the correct direction*. A reported association pointing
  the wrong way is a false positive, not a partial credit.
- **Recall** — of the injected relationships, the fraction reported.
- **False discovery rate** — the empirical FDR of D's SUPPORTED set, compared against
  the nominal alpha. This is the one number that directly tests the project's central
  claim, and it is only computable because the truth is planted.

Report all three per condition, with the n=40 power limitation stated plainly
(`PROJECT.md` §6 already commits to that framing).

## 4. The four conditions are flags, not codebases

One pipeline, four settings. Any other arrangement risks the conditions differing in
something other than the variable under study.

| Condition | Analysis loop | Gate | Notes |
|---|---|---|---|
| A | off — single LLM call | none | the naive baseline |
| B | on | none | agent loop, everything it proposes is reported |
| C | on | **judgement, not execution** | same model, same claims, same information; asked to decide instead of testing |
| D | on | full gateway | `verify_batch` |

**There is no LLM critic in the product.** Condition C is an evaluation mode only.
A second model inside the product would muddy the design, and a critic that saw the
observed statistics before filtering would reintroduce exactly the peeking problem the
no-re-testing rule exists to prevent (`PROJECT.md` §2).

C must be built honestly (`docs/OPEN_ISSUES.md` issue 3): same model, same context, a
prompt written to make it succeed. Beating a strawman proves nothing, and it is the
first thing a reviewer will probe.

## 5. What must be logged per run

Enough to re-derive every number in the results table without re-running anything:
dataset id and build seed, injected truth table, condition, model and generator,
gateway config snapshot (alpha, `n_permutations`, seed, thresholds), and every proof
object. `bh_family_id` ties each verdict to the exact family it was corrected within.

## 6. Open, needs the team

- Where the 40 extracts come from, and who screens them for contamination — that is
  P. Rohith's benchmark curation (`scope/SCOPE_P_Rohith.md` component 6), and it needs
  to produce the *pre-shuffle* extracts this spec consumes.
- Whether the one or two demo datasets keep real, published relationships (they should:
  the demo is about showing a real finding survive and a planted fake die), while the
  40 benchmark datasets are fully synthetic-by-construction. Confirm both audiences are
  happy with that split before the report is written.
