# Proposal: small tables (for the verification owner's sign-off)

Status: proposal only. Nothing below except option A is implemented. Options B to E touch
AGENTS.md §8.10 areas or add a report section, so they need the owner's decision.

## What happens today

Found by running the real 51-state US crime table (`statsmodels` `statecrime`) through the
live app on 2026-10-25.

- The planner reads only the exploration half of the rows. Here that was 25 of 51.
- A claim needs `hypotheses.min_observations` = 30 complete rows in that half, so every claim
  was dropped. The tab showed "not renderable", which was the wrong reason.
- Measured needs `min_rows` = 60, so all four model results were "not run".
- The Exact tier ran outliers and data quality only. Strong relationships in the data
  (murder vs single parents, Spearman 0.78; vs poverty, 0.66; vs graduation, -0.76) appeared
  nowhere. The report looked empty although every printed number was correct.

A table needs roughly 60 or more rows to get any tested claim, and 60 or more to get models.

## Option A: honest reason (done, no sign-off needed)

Dropped claims now say "only N complete rows are in the exploration half of the table and 30
are needed to propose a claim; the other half is kept back for the strict test". The Checked
claims tab says the table is small and points to the Report tab. Code: `_thin_exploration` in
`src/pramana/analysis/planner/planner.py`, drop reason `too_few_rows`.

## Option B: a descriptive association table in the Exact tier (recommended)

A new Exact figure, "How the numeric columns move together": Spearman rank correlation on the
whole table for each pair, strongest first, n beside each, no p-value and no verdict, labelled
"described, not tested". Pairs of the same quantity and bookkeeping pairs are filtered by the
existing `claim_filters`. It is arithmetic, so it fits the Exact tier and does not touch the
gate. Caveat to state on screen: with many columns some large values arise by chance, and
none of it is a tested claim.

Cost: about a day including tests and the recall script. Risk: users read "described" as
"proven"; the wording must stay explicit.

## Option C: lower the proposal floor from 30 to 20 exploration rows

`hypotheses.min_observations` 30 to 20, matching the gateway's own floor
(`verification.yaml` `min_observations: 20`). Tables of about 40 rows would get claims. Not a
gate threshold, but it changes how many claims enter the BH family and how weak the proposing
half can be, so the owner should decide. Effect on the evidence cards is untested; the gate
report card would need re-running at n = 40.

## Option D: a different split for small tables (for example 60/40 or 50/50 with a larger
confirmation half)

Gate area (§8.10). Not changed, as instructed. Listed because the real constraint is the
halving itself.

## Option E: test the whole table with no held-out half, labelled exploratory

Allows claims on tables under 60 rows. The same rows would both propose and test a claim,
which removes the protection against picking the best-looking pair. Not recommended for
verified status. It could be offered only as "exploratory, not eligible for memory".

## Recommendation

Keep A. Build B next. Decide C only after re-running the gate report card at n = 40 to 60.
Leave D and E out unless the thesis needs small-table claims.
