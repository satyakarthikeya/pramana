# Plan: make PRAMANA work like a data analyst (gateway last)

Status: PROPOSAL, 2026-10-24. Written after a review of the live demo on real data
(UCI Online Retail II). Build order: the analyst first, the verification gateway last.

## 1. The problem, stated plainly

The demo reports things like "revenue is positively associated with orders" and
"quarter is positively associated with customers". A correlation matrix already shows
these. They are either bookkeeping (revenue is built from orders) or a time label treated
as a variable. A reviewer will ask "what is the use of this?" and be right.

Cause: the planner can only choose from five tested claim types (association, group
difference, trend, period change, seasonality), so it mostly proposes pairwise
associations, and the gateway then verifies questions nobody needed answered. The
descriptive tier (period change, what accounts for the change, concentration, margins,
outliers) is real analysis, but it is not organised into a story and it stops short of
what an analyst reports (price versus volume, a forecast, a "so what").

## 2. What a data analyst does with a finance table (the target behaviour)

1. **Frame the question.** What happened, why, what is next, who or what stands out.
2. **Headline numbers.** Totals, growth, margin, versus the previous period or year.
3. **Explain the movement.** Which segments drove it; price versus volume versus mix;
   cost against revenue; one-off items.
4. **Find what is unusual.** Spikes, drops, a segment that diverges, customers that
   matter.
5. **Look ahead.** Seasonality, a forecast with a range, whether it beats a naive guess.
6. **State caveats and ask the next question.** Data gaps, what could not be checked,
   what to look at next.

PRAMANA should produce exactly that sequence, with every number computed by code and every
sentence traceable to a figure.

## 3. Design: a closed menu of analyses, chosen by the question, run by code

Rule kept from AGENTS.md section 2: **models propose, code computes and decides.** The
model never writes a number or a sentence the user reads as fact.

```
question + table
  1. PROFILE      shape, sector, roles (exists)
  2. PLAN         the planner picks analysis ids and columns from a closed menu
                  (exists for claims and models; extend the menu, section 4)
  3. COMPUTE      code runs each analysis -> a Finding with its numbers (exists / extend)
  4. RANK         code scores findings; drops bookkeeping and duplicates (new)
  5. STORY        what happened / why / what to watch / what to ask next (new layout)
  6. DRILL        one optional second round: the planner asks for a drill-down into
                  something it saw in step 3 (new, closed menu, max 2 rounds)
  7. TEST         only findings that make an inferential claim go to the gateway (last)
```

### Finding (the unit that moves through the pipeline)

`id, kind, title, numbers{...}, columns, rows_used, sentence (code-written),
materiality (share of total), change, surprise, evidence_level (exact | measured | tested)`.
The Exact and Measured tiers already produce items of this shape; this step gives them a
common ranking and layout.

## 4. The analysis menu for finance (what to build, in order of payoff)

| # | Analysis | Status | Notes |
|---|---|---|---|
| A1 | Headline KPIs and year-on-year / fiscal-year change | exists (`period_change`) | add margin and share lines to the headline |
| A2 | What accounts for the change, by segment | exists (`variance_decomposition`) | fix wording for units/orders; show top 3 movers up and down |
| A3 | **Price / volume / mix bridge** | NEW | revenue change = volume effect + price effect + mix effect, from quantity and unit price per segment; plain arithmetic |
| A4 | Margin bridge (revenue vs cost) | partly (`margins`) | add the cause: price, volume, mix, or cost rate |
| A5 | Concentration, Pareto, top-N movers | exists | add whether concentration is rising |
| A6 | **Seasonality on any 24+ consecutive months** | BUG to fix | today it needs two calendar years; use month-of-year over rolling 12-month blocks |
| A7 | Row-level anomalies with the reason | exists | reword ("26 against a usual 4,000"), group by cause |
| A8 | **Forecast headline** | exists in Measured, not surfaced | next 3 periods with an interval, and whether it beats seasonal-naive |
| A9 | **Segment growth comparison** | NEW | growth rate per segment, ranked, with the spread |
| A10 | **Customer view** (transactions with a customer id) | NEW | repeat share, top-customer share, new versus returning revenue |
| A11 | Drivers of the target (Measured) | exists | keep as a secondary section |
| A12 | Data quality and caveats | exists | always shown last |

A3, A6, A8 (surfaced), A9 are the highest value for a finance demo and are all arithmetic or
an existing Measured result.

## 5. Ranking and removing noise (code, not prompts)

Rules, all in code with thresholds in `configs/analysis.yaml`:
- **Bookkeeping filter.** Drop a pairwise claim when one column is a component of the
  other under the sector roles (quantity, orders or customers against an amount).
- **Time-label filter.** A time column or a quarter/month label is never a variable in
  an association; time questions become trend or seasonality.
- **Materiality.** A finding's share of the total (for example a segment holding under a
  small share of revenue) lowers its rank; the UK at 66% of the rise leads.
- **Dedupe.** Revenue, units and orders often tell the same story; show one and list the
  others as "also".
- **Pairwise associations** move to a secondary section titled "Relationships".

## 6. The story layout (what the report page shows)

1. **What happened** - 3 to 5 headline findings (A1, A4 headline, A8 headline).
2. **Why** - A2, A3, A9, A5.
3. **What stands out** - A7, A10, seasonality (A6).
4. **What to watch next** - generated questions from the findings (code templates), for
   example "Denmark fell by 220k: is that a lost customer?". Questions, not advice.
5. **How sure** - which findings are exact, which are measured, which passed the gateway.
6. **Caveats** - A12 and anything that did not run, with the reason.

The existing code-written summary and the DeepSeek reword (validated: every number must
match a displayed figure, no causal wording) are reused; only the inputs and order change.

## 7. The analyst agent (the "agent" part, kept safe)

- **Round 1:** planner chooses analyses from the menu (extends today's planner).
- **Round 2 (new):** the planner sees the ranked findings and may request up to a few
  drill-downs from the same closed menu with a filter chosen from the table's own levels
  (for example A2 restricted to the top mover, A7 for one country). Code validates every
  request; nothing free-form runs.
- Traced through Langfuse under the run id like every other model call; fails closed.

## 8. What goes to the gateway (last)

Only findings that claim something beyond the table:
- seasonality of the main amount;
- a trend over time;
- "segment A grows faster than segment B" (A9) as a tested difference;
- "concentration is rising";
- "the forecast beats the naive baseline" (from A8).

Pairwise associations are tested only when they survive the bookkeeping filter. The
gateway work already done (nulls, split, power note, interval, attacks, refuter) is
unchanged and is exercised by these claims.

## 9. How we know it works like an analyst (the thesis figure for this layer)

**Planted-fact recall.** Build 5 tables with known facts (for example: South grows
fastest; October to December is 35 percent higher; the Lite product's margin falls;
one row is 6 times too large; one country collapses). Score the report on whether each
planted fact appears in the top findings with the right numbers. Report recall and the
number of irrelevant findings per report, before and after this plan. The synthetic
finance table and the real retail data are the first two cases.

## 10. Order of work

**Today (about 6 to 7 hours):**
1. Bookkeeping and time-label filters in code, plus ranking and the "Relationships"
   section (1.5 h).
2. A6 seasonality fix for rolling 24 months (1 h).
3. A3 price / volume / mix bridge with a known-answer test (2 h).
4. A8 forecast headline surfaced in the story (1 h).
5. Story layout and code-written "what to watch" questions (1.5 h).

**Tomorrow morning:**
6. A9 segment growth comparison, then its tested claim (2 h).
7. A10 customer view for tables with a customer id (1.5 h).
8. Planted-fact recall check on the five tables (1.5 h).

**Tomorrow afternoon:** rerun the retail and finance demos, fix what breaks, screenshots,
sign-off sheet update. Drill-down round (section 7) only if time remains.

## 11. Risks and honest limits

- Price / volume / mix needs a quantity and a unit price (or revenue and quantity); tables
  without them get a clear "not run" reason.
- The planted-fact check shows the pipeline surfaces known facts. It does not show it
  finds true unknown ones, and the finance table is synthetic.
- Ranking weights are provisional and live in `configs/analysis.yaml`; they need review.
- Wording of "what to watch" must stay questions; the platform gives no investment advice.
- The model's role stays: choose from a closed menu and (optionally) reword code-written
  sentences under validation. It does not compute or conclude.

## 12. Tools and machine learning inside the analyst (added at the owner's request)

What exists today (checked in the code):
- **Python workspace** (`analysis/workspace`, `docs/ANALYSIS_AGENT.md`): the agent can run
  small numpy / pandas programs in a sandbox, plus fixed tools (`describe`, `compare_groups`,
  `relate`, `trend`, `missingness`). It is OFF by default (`workspace.sandbox.enabled`) and
  allows only numpy, pandas and the vetted stats library. scikit-learn is not allowed there.
- **Measured tier** (`analysis/measured`): a closed menu run by trusted code with nested
  cross-validation, a baseline and a leakage check: ridge, random forest, gradient boosting,
  SVR / SVC (the SVM), logistic regression, KMeans segments, IsolationForest anomalies,
  Holt-Winters / seasonal-naive forecasts, a piecewise threshold.

What to add (choice A, recommended, safe and testable):
| Tool | Use for the analyst | Effort |
|---|---|---|
| **Segment profiles** on KMeans | name each cluster by how it differs from the whole ("segment 2: 9% of customers, 41% of revenue, 3x the order size") | 2 h |
| **KNN** (regressor / classifier) added to the driver menu, and "customers like this one" | a model family to compare against SVM / forest; nearest-neighbour baseline | 1 h |
| **Hierarchical or DBSCAN** clustering as a second view | check that segments are stable across methods | 1.5 h |
| **PCA** with parallel analysis | which columns move together; stability by bootstrap | 1.5 h |
| **RFM** (recency, frequency, monetary) for tables with a customer id | the classic customer analysis | 2 h |

All are added to the closed menu, run by code, scored on held-out rows against a baseline,
and described by code-written sentences. The model only chooses which to run.

Choice B (not recommended before the review): let the agent write scikit-learn code in the
sandbox. It needs the sandbox import list widened, which is a change to AGENTS.md section 4
(execution safety) and needs the verification owner's approval. Its output could only ever be
shown as "exploratory, not verified", with the code visible.

Honest limit: KNN, SVM and clustering are worth adding only where they answer a question
the analyst would ask (who are the customers, what predicts revenue, what is unusual). Their
value is the interpretation, not the algorithm count.
