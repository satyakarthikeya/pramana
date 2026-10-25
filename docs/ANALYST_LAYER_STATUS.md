# Analyst layer: what is built, what was measured, what is not done

> **Status of one change (PR #31).** Current project status is in [STATUS.md](../STATUS.md). Figures and branch names below are from the date of writing and may be out of date.

Branch `feat/satya/analyst-layer` (from `feat/satya/finance-f3-f7`). Plan: `PLAN_data_analyst.md`.
Nothing here changes the gateway, a p-value, FDR, the sandbox or memory.

## Built (Exact tier, code only, no model)
| Item | What it does |
|---|---|
| Price / volume / mix | Splits the change in an amount into volume, price per unit and mix; the parts add up to the change exactly (asserted). Segments present in only one window get their own line. |
| Segment growth | Growth rate per segment between the two windows, ranked; segments under 2% of the earlier total are not ranked and are counted. |
| Customer view | Top-N and top-tenth share, repeat share, new vs earlier customers in the latest window; rows with no id are left out and reported. A numeric `customers` count column is not treated as an id. |
| Seasonality | Now runs on any 24+ consecutive months (ratio to a centred moving average), so a financial-year table works; the old calendar-year path is kept when two full calendar years exist. The sentence says how many times each month was seen. |
| Story | Figures grouped as what happened / why it moved / what stands out / checks; the same story on other measures is shown once with the rest under "same question on N other measures"; a margin or season that barely moves no longer leads. |
| What to watch next | Up to 5 questions written from templates using each figure's own numbers. Questions, not advice. |
| Claim filters | A correlation between an amount and what it is made of (orders, units, price, cost, profit) or against a time label (quarter, month, year) is dropped by the planner before the gate, with a recorded reason. |

## Built (Measured tier and customers, added after the first version of this note)
| Item | What it does |
|---|---|
| Segment profiles | Stable KMeans segments now say what sets each apart (standard deviations from the overall mean) and its share of the main amount. A grouping that is not stable is still reported as "no stable segments". |
| Nearest neighbours (KNN) | Joins the closed driver menu beside ridge, forest, boosting, SVM and logistic; scored on held-out rows against the baseline like the rest; left out above `knn_max_rows` (20,000). |
| Components (PCA) | New measured kind. Components are kept only where their eigenvalue beats the 95th percentile of column-shuffled copies (parallel analysis) and the kept components reappear when rows are resampled. The planner may ask for it. |
| RFM | Exact tier: recency, frequency (periods with a row, because the table has no orders) and money per customer, scored 1-5 by average rank (equal values score alike), grouped by fixed rules. Known-answer test on 60 planted customers. |

Weights and limits: `configs/analysis.yaml` (`computed.story_weights`, `lead_items`, `max_questions`,
`segment_growth_min_share`, `customer_*`). They are provisional and only order the reading.
`COMPUTED_VERSION` is 6; old stored reports are rebuilt.

## Measured
`scripts/calibration/analyst_recall.py`: six seeded synthetic tables, each with one planted fact
(a product's margin falls, Q4 +35%, one row 6x, a segment collapses and another grows, price up
and volume down, ten customers make half).

| | Facts surfaced in the top 8 |
|---|---|
| Before this branch | 3 of 7 |
| After | 7 of 7 |

Read with care: the tables are synthetic, I wrote them and the figures that find them, and the
check shows the report surfaces KNOWN facts. It does not show it finds unknown ones. The
"off-topic" count the script also prints is not a quality measure (it counts lead figures not tied
to the planted fact, which includes useful ones such as the period change).

Real data (UCI Online Retail II, customer x month x country, 25,073 rows): lead is revenue +6.1%,
the UK is 66.2% of the rise, price/volume/mix, growth by country (EIRE -25.1%), customers (top
tenth = 63.6% of revenue), a single 376,033 row that is 1,096x its country median, November at 1.76x.
Checked in the running app. "Price" there is average price per unit within a country, so it also
moves when the products sold inside a country change; the sentence says so.

## Not done
- Forecast headline from the Measured tier is not moved into the story (still under the planner's
  analyses at the bottom of the results page).
- Hierarchical / DBSCAN clustering (plan section 12) and the drill-down round.
- KNN, components and segment profiles are tested on planted tables and run on the real retail tables; there is no head-to-head showing KNN is chosen when it should be.
- On the customer x month retail table the Measured tier has only two numeric columns, so models, segments and components do not run there; on the country x month table components found one direction (79.4% of the variation, orders/units/customers) and segments were not stable.
- A9 / "concentration is rising" as tested claims for the gateway.
- The deterministic proposer does not use the claim filters (the planner path does).
- The DeepSeek reword of the summary fell back to code wording on the retail table ("a number that
  is not in the figure"); not investigated.
- A partial last period (a table that ends mid-month) is not detected.
- Report page not checked at phone width.
