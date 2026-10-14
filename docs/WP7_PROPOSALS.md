# WP7 proposals (for the owner's decision; no code changed for items 1 and 3)

## 1. `outlier_warning` -- proposed threshold and wiring

**Status quo (confirmed).** `ProofObject.outlier_warning: bool = False` already exists
(`contracts/proof_object.py:114`), so setting it is NOT a contract change. Only the correlation
template emits `outlier_divergence` (`templates.py:106`, `|pearson_r - spearman_rho|`); the trend
and group templates do not, and `gateway.py` never reads the key. Nothing sets the flag.
Note the field's description ("moved materially when outliers were trimmed") does not match
what is measured (rank-vs-linear disagreement); fixing the wording is a contract-text change
and would need announcing (AGENTS.md 8.7).

**What it measures.** `|r - rho|`, in [0, 2] but in practice [0, ~1]. Large means a handful of
points carry the linear estimate while the rank view disagrees.

**Measured distribution** (script: scratchpad `od.py`; 400 draws per cell; quantiles are
p50 / p95 / p99 / max):

| case | n | p95 | p99 | max |
|---|---|---|---|---|
| toy frame: age~bmi, month~visits, decoy, noise | 240 | single values: 0.043, 0.016, 0.025, 0.008 | | |
| Gaussian, true rho~0.45 | 100 | 0.071 | 0.102 | 0.166 |
| Gaussian null | 30 / 100 | 0.134 / 0.057 | 0.168 / 0.075 | 0.200 / 0.104 |
| log-normal x (curved, real) | 100 / 240 | 0.188 / 0.167 | 0.234 / 0.234 | 0.260 / 0.263 |
| heavy tail, t(df=2) | 100 / 240 | 0.368 / 0.297 | 0.537 / 0.387 | 0.622 / 0.461 |
| ONE planted leverage point on null data | 30 / 100 / 240 / 1000 | 1.14 / 1.00 / 0.87 / 0.50 | | min 0.47 across all n |

**Proposal.** New key `evidence.outlier_divergence_warn: 0.30` in `configs/verification.yaml`,
placed next to `effect_thresholds` (a plain float, `gt=0, lt=2`, no default, same
`extra="forbid"` loader). Justification: 0.30 sits roughly 7x above every toy-frame value, above
the 99th percentile of Gaussian and log-normal data at n>=100 (max 0.26), and below the weakest
single-leverage-point case measured (0.47). Genuinely heavy-tailed data (t2) trips it about 20 to
30% of the time, which is the intended reading ("linear view is fragile"), not a false alarm. It
is a REPORTING flag: it must never gate, matching the existing `effect_size.py` docstring and
the "gate and score are separate" rule. Like every other band it is PROVISIONAL until calibrated
on real NHANES (OPEN_ISSUES 11).

**Wiring.** `gateway.py` `_build_proof`: `outlier_warning = payload.get("outlier_divergence",
0.0) > config.evidence.outlier_divergence_warn`, passed to `ProofObject(...)`. Missing key (trend,
group templates; LLM-written code that omits it) means False. Open choice: also emit
`outlier_divergence` from the trend template (tau-vs-Pearson would need a new definition, so I
suggest correlation-only for now and say so in the doc).

**Files / tests.** `configs/verification.yaml`, `verification/config.py` (`EvidenceConfig`
field), `gateway.py`, `tests/fixtures/config.py` pinned config if it copies keys, new tests:
config rejects missing/negative key; gateway sets True on a planted leverage frame and False on
the toy frame; flag never changes verdict. `test_gateway_e2e.py` unaffected. Wording fix for the
field description is the only (optional) contract touch.

## 2. `MIN_OBSERVATIONS` duplication -- done (no config/gateway edit needed)

Three identical hardcoded 3s (`effect_size.MIN_PAIRED_OBSERVATIONS`, `permutation.MIN_OBSERVATIONS`,
`bootstrap.MIN_OBSERVATIONS`) are now one `effect_size.MINIMUM_COMPUTABLE_OBSERVATIONS`, imported by
the other two. Messages and boundaries are byte-identical. `statistics.min_observations: 20` is
untouched and stays the only conclusion threshold. Side finding: the pooled-total check in
`permutation_test_groups` can never fire (two groups of >=2 already total 4); left as is,
pinned by a test.

## 3. Cramer's V (OPEN_ISSUES 10) -- options, your call

Decision needed: `cramers_v` is banded, gated and tested but no claim type can reach it.
(a) Add a `categorical_association` claim type: contract change (`ClaimType`/`CandidateInsight` in shared `src/pramana/contracts`, must be announced), plus template, prompt, admissibility, table-permutation in stats, and analysis-agent support; cost: large, multi-owner, ~1 phase.
(b) Declare it out of scope: mark `cramers_v` unreachable in `docs/SCOPE.md` and OPEN_ISSUES 10, keep the band and its tests; cost: about 30 minutes, no code, and area x education style findings are not testable.
Recommendation: (b) now, because the demo's claims are covered by the four live metrics and (a) is a contract change; revisit (a) after the first NHANES calibration.
No code changed; stopping here until you decide.
