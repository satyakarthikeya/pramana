# Cross-domain Ask and website acceptance — 25 October 2026

## Scope and method

This extends the previous health-fixture checks. It is a finite acceptance matrix,
not proof that every dataset or natural-language question works. Inputs are newly
generated synthetic manufacturing, retail and sensor tables, each with 120 original
rows and fixed seed 20261026. Independent reference answers are calculated from the
CSV bytes. No participant records or user uploads are sent in these tests.

The existing personal preview on port 8087 is preserved. An isolated website on
port 8088 uses a separate local account and data store. Its configuration uses
DeepSeek for the analyst agent, test-code generation, sector reader and summary,
with Langfuse enabled. Uploads and questions are submitted through the actual React
forms in a real Brave/Chromium browser. API reads only observe background run state.

Windows computer-use could read the browser, but could not reliably target its native
file-picker controls. The acceptance driver therefore uses Playwright with a separate
headless browser context, the real website, and screenshots. Playwright 1.64.1 was
installed only under ignored `artifacts/browser-tools`; application requirements and
dependencies were not changed. No visual/manual cross-device acceptance is implied.

## Reproduced failures and general fixes

1. The website refused machine speed/defect rate when columns were camelCase with
   unit suffixes. Seven naming regressions failed before the fix. Chat now separates
   camelCase/acronyms and optional units, recognises explicit unit qualifiers, and
   keeps ambiguous units unresolved. This is a lexical rule, not a dataset-name or
   question-specific response. Existing whole-phrase and unrelated-claim checks remain.
2. Tools could not supply sums. A known-answer totals test failed before the fix.
   `describe` and `compare_groups` now compute numeric sums; the model is instructed
   to cite these values instead of multiplying means/counts or substituting a mean.
3. A future-prediction request returned present-day summaries without an explicit
   capability explanation. Ask now states that it has no forecast tool and runs no
   unrelated association test as a substitute. Report forecasting remains separate.
4. Duplicate removal silently changed the scope of chat totals. Ask now displays a
   code-written cleaning note beside the answer, including uploaded/retained counts
   and a warning about distinct records with identical values. The note is persisted
   and survives history rendering. The cleaning policy itself is unchanged.

No p-value, FDR, threshold, split, sandbox or PASS-only memory policy changed.

## Important retail finding: original versus cleaned rows

The initial retail fixture has 120 orders described only by quantity, price, revenue
and region. Thirty-one rows are identical. Under the existing cleaner, 89 remain:

| Quantity | Original CSV | Cleaned table |
|---|---:|---:|
| Rows | 120 | 89 |
| Revenue total | 25,520 | 18,080 |
| Mean unit price | 20.4166667 | 19.8876404 |
| Highest-revenue region | West: 8,890 | North: 7,130 |

The first browser pass failed three independent original-file numeric checks. Those
failures remain in `final/results.json`; they are not relabelled as original-file
passes. A separate, explicitly scoped check compares cleaned arithmetic and requires
the cleaning warning to be visible.

A fourth fixture, `retail_identified.csv`, adds unique order record identifiers to
the same orders. All 120 rows then remain, and the original-file calculations match.
The system cannot determine from equal values alone whether rows are duplicate errors
or legitimate separate transactions. Users must confirm deduplication or supply row
identity; a general interactive cleaning-policy decision remains outside this fix.

## Browser checks and evidence

The baseline manufacturing pass reproduced the failed association-name match while
its average-temperature answer was correct. The first fourteen-question pass then
exposed the retail scope mismatch and the inadequate forecast response.

The next nineteen-question pass across four tables passed the intended checks,
including explicit scope for the unlabelled retail data. The final repeat adds page
reloads, exact executed-code display in proof drawers, and visible cleaning notes.
Its first attempt found two code panels (Python and raw JSON); that test-selector
failure required no application change. The repeat targets the Python panel explicitly.

Expected arithmetic includes manufacturing mean ambient temperature 23.6629853415;
manufacturing speed/defect Spearman -0.9768108896451142; identified-retail total 25,520
and West total 8,890; sensor mean Celsius 22.5919415496. Questions also cover:

- Ordinary names, camelCase identifiers and explicit units.
- Causation and generalisation alongside an association test.
- Missing columns and requests to invent a revenue total.
- Ambiguous temperature units and explicit Celsius selection.
- Future prediction without a forecasting tool.
- Proof opening, the saved code, and persistence after reloading.

Ignored evidence lives under `data/acceptance/cross-domain-web/`: `answers.json`,
`baseline/`, `final/`, `verified/`, `confirmed/`, screenshots and browser test receipts.
The browser cookie file is private test state and must never be committed or printed.
Runner and audit scripts are under ignored `artifacts/`.

Final browser repeat: **19/19 scenarios passed** across four tables in three domains.
Every answer matched its API response in the UI and survived page reload. All five
tested claims opened their proof drawers and displayed exactly the saved Python
source. Cleaning warnings were checked as visible UI elements, not just JSON fields.
The ambiguous-unit and forecast questions used no model or gateway calls.

Readable answer-card screenshots are in `answer-cards/`, including
`10-retail.png` (cleaning warning), `5-retail_identified.png` (original-file total),
and `18-sensors.png` (forecast limitation). Desktop screenshots were inspected; this
does not constitute keyboard, mobile or comprehensive accessibility acceptance.

Independent final audit (`artifacts/cross_domain_audit.json`): five programs replayed
exactly in the sandbox, reproducing p/effect/metric/reported-effect fields. SciPy
Spearman effects match within 1e-12, and every chat q equals p:

| Test | Independent rho | p = q | Verdict |
|---|---:|---:|---|
| Machine speed / defects (asked twice) | -0.9768108896451142 | 0.00009999000099990002 | PASS |
| Identified orders: quantity / revenue | 0.8047888390827261 | 0.00009999000099990002 | PASS |
| Deduplicated orders: quantity / revenue | 0.8190056829542457 | 0.00009999000099990002 | PASS |
| Celsius / independent humidity | -0.10895895548301962 | 0.23047695230476953 | REJECT |

Remote Langfuse metadata confirms seventeen message traces and 45 model requests,
67,312 input tokens and 2,990 output tokens, all `deepseek-flash`. Cost is unknown.
The local memory endpoint contains four analysis lessons, all PASS, and none tied to
these chat message IDs. The replay/metadata audit made no new inference requests.

The personal preview on port 8087 was restarted after confirming no active analysis
runs. Existing accounts/uploads/history were preserved; `/health` returns HTTP 200.
Nothing was staged, committed or pushed for this follow-up.

## Verification status

Targeted chat/workspace/API checks: 153 passed, two existing warnings. A final focused
check of chat behavior and cleaning-note persistence passed 95 tests. Ruff and source
mypy (174 files) pass. The verification partition passed all 466 tests with three
existing warnings in 806.42 s (`artifacts/cross_domain_suite_verification.log`).
The final application partition passed 893 tests with twenty existing warnings in
919.19 s (`artifacts/cross_domain_suite_application_confirmed.log`). Together these
disjoint partitions cover the complete suite: **1,359 passed**, 23 existing warnings;
independent collection confirms exactly 1,359 tests. Interrupted application-suite
runs are not counted. No source changes followed the final application partition's
start; the verification partition covers unchanged verification code.

Existing warnings include pytest collection of imported enum types, a pre-existing
test helper returning a dictionary, and dependency deprecations. They are not claimed
as fixed. `git diff --check` passes. No frontend source changed in this follow-up, so
the previously built UI was exercised directly rather than rebuilt without a change.

The isolated test server on port 8088 was stopped after browser/audit completion to
release resources. Its data, reports, model cache and screenshots remain intact. The
personal preview on port 8087 remains running.
