# PRAMANA V2 — Evaluation plan (parked)

Status: PARKED on 2026-10-23 at the user's request ("keep evaluation afterwards"). Build
work goes first; this file is the agreed design for when evaluation starts. The phase
gates in `docs/PLAN_analysis_platform.md` §9 still refer to these suites.

## 1. Two kinds of evidence

1. **Planted suites** score the gate: we generate data where we know the truth.
2. **Answer-accuracy suites** score the platform's answers item by item against a gold
   answer, like InfiAgent-DABench.

Only planted data can prove a false-positive rate. Published-result datasets prove the
arithmetic and the descriptive answers.

## 2. Planted suites

Every effect is a multiple of the gate floor, resolved at build time. Seeds:
`SeedSequence([20261001, suite_code, i])`, so suites never share a seed.

| Suite | Recipe | Reuse | Datasets |
|---|---|---|---|
| S0 | NHANES pilot extract, shuffled, k = 0 | `planted.py` | 200 |
| S0-rw | half: X, Y independent Gaussian random walks, n ∈ {24, 60, 250, 1000}; half: one walk vs time | new | 200 |
| S0-panel | E ∈ {8, 20} entities, T ∈ {12, 36}; X = a_e + ε, Y = b_e + ε, a_e and b_e independent | new | 200 |
| S1 | monotonic / shift / trend at {0.7, 1.25, 1.8, 2.5}× floor | `planted.py` | 200 |
| S1-atk | per attack: a case it must catch and a truth it must spare (A1 extreme points vs t₃ tails, A2 last-quarter-only vs stationary, A5 ties vs linear, …) | new | 140 per case |
| S2 | Z→X, Z→Y, no X→Y, marginal ρ = 2.5× floor; control: X→Y with unrelated Z | new | 140 |
| S3 | Simpson: within-group ρ = −1.8× floor, pooled +2.5× floor | new | 140 |
| S4 | effect only in one level (30% of rows) | new | 140 |
| S5 | Y = Σ 0.2·Xᵢ over 3 drivers + 7 noise columns | new | 140 |
| S6 | 0.5 SD step at a breakpoint in the 0.3–0.7 quantile range | new | 140 |
| S7 | `net = rev − cost` identity and a target proxy | new | 100 |
| S8a | 12 months × 5 regions: +15% YoY, region A ≥ 60% of growth, expense spike (robust z ≥ 6), December +30%, one random-walk column. Tested must say "too few periods" | new | 140 |
| S8b | same plants, 3 years daily × 5 regions | new | 140 |
| S9 | k ∈ {3, 4} clusters, 3 SD apart, 6 dims; plus no-cluster control | new | 140 + 140 |

Counts: a ±0.05 95% CI on a proportion near 0.9 needs about 140 cases. 200 null
datasets do not certify FWER ≤ 0.05; they detect a doubling (0.10) with about 85%
power. Bounds are computed in code (`binomtest(...).proportion_ci('exact')`) and CIs
over cases use a cluster bootstrap over datasets.

Truth format: `TruthRowV2` (adds `kind`, `control_column`, `subgroup`) and a `facts[]`
list `{fact_id, kind, value, tolerance, expected_tier}`. The existing frozen `TruthRow`
is not extended in place.

## 3. Targets

| Metric | Target |
|---|---|
| All-null suites: fraction of datasets with ≥ 1 PASS | ≤ α (0.05), exact upper bound reported |
| Mixed suites: mean FDP, before and after attacks | ≤ α |
| Null p-value calibration (KS vs uniform) | not rejected at 0.01 |
| Confounder rejection (S2) | ≥ 0.90 |
| Attack power on its planted case | ≥ 0.80 each |
| Joint false-kill of the attack set on true findings | ≤ 0.15 |
| S8a Exact facts | 3 of 3 on ≥ 90% of datasets; 0 Tested claims |
| S8b all tiers | ≥ 4 of 5 facts on ≥ 90% of datasets |
| Leakage lint (S7) | 1.00 on identities, ≥ 0.90 on proxies |
| Reproducibility | identical numbers for the same seed, 100% |

## 4. Answer-accuracy benchmark

Item: `{id, dataset_id, sector, question, answer_format, gold, tolerance,
expected_level: E|M|T|REFUSE, category, source}`. `answer_format` uses DABench's
`@name[value]` convention. Gold comes from an independent reference script or from a
published source, never from the platform.

| Suite | Content | Checks |
|---|---|---|
| QA-dabench | InfiAgent-DABench closed-form questions, famous CSVs removed | descriptive accuracy; external comparison only (public, may be in DeepSeek's training data) |
| QA-finance | ~300 questions on S8a/S8b, Online Retail II, Census retail | finance Exact and Measured answers |
| QA-health | questions whose gold is a published CDC / NFHS-5 figure | health Exact answers (needs survey weights) |
| QA-tested | yes/no questions whose gold is a planted truth | Tested tier precision and recall |
| QA-refuse | causal, too-few-points, leakage-target, missing-column questions | correct refusal; a number given here is scored wrong |

Scoring: per item; accuracy per suite and category; DABench's three metrics on
QA-dabench; refusal precision and recall. Targets: QA-finance Exact ≥ 0.95;
QA-refuse ≥ 0.95 correct refusals with ≤ 0.05 false refusals.

## 5. Datasets per sector

All licences marked "to verify" must be checked on the source page before use, and
the result recorded in the manifest. Raw data lives in gitignored `data/eval/`.

### Finance

| Dataset | Gold from | Licence |
|---|---|---|
| US Census Monthly Retail Trade (MRTS) | published monthly and YoY % changes | US Government work (to verify) |
| SEC EDGAR financial statement data sets | accounting identities in filings | public (to verify) |
| TAT-QA / FinQA | published Q&A over financial tables, with baselines | to verify; contamination risk |
| UCI Online Retail II | independent reference script | CC BY 4.0 |
| GST state collections (data.gov.in only) | published monthly totals | GODL-India if on data.gov.in (to verify) |

### Healthcare

| Dataset | Gold from | Licence |
|---|---|---|
| NHANES 2017–18 | CDC NCHS Data Briefs (weighted prevalence) | US federal, public domain |
| NFHS-5 district factsheets | the published indicators | GODL-India |
| CDC BRFSS | CDC published state prevalence tables | public (to verify) |

### Panels for nulls

World Bank WDI (CC BY 4.0), Eurostat retail turnover (CC BY 4.0).

### Excluded

FRED (terms forbid caching and ML use), NFHS-5 / DHS microdata (redistribution
banned), DSBench (data not licensed), MIMIC-IV (`AGENTS.md` §6).

## 6. Layout

```
data/eval/                      # gitignored
  raw/<source>/<version>/
  extracts/<dataset_id>/{data.csv,metadata.json}
  synthetic/<suite>/<i>/{data.csv,truth.json}
  qa/<suite>/items.jsonl
configs/eval_manifest.yaml       # committed: source, licence, sha256, shape, suites, controls
```

## 7. Minimum set to start

S0 and S1 on the NHANES pilot extracts; new generators for S0-rw, S0-panel, S2, S8a,
S8b; Online Retail II as one real finance check; QA-refuse; a runner that writes the
V1 baseline table.
