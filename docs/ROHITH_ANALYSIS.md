# P. Rohith — Data Analysis Module

This module owns the proposer-side data path:

```text
CSV/XLSX input
  -> bounded ingestion and metadata
  -> conservative cleaning and audit report
  -> descriptive profiling and exploratory relationship evidence
  -> schema inference (column roles)
  -> CandidateInsight generation  ->  verification gateway
```

> Last updated 2026-09-18. Schema inference and CandidateInsight generation were
> built by P.P. Satya Karthikeya by team agreement (see *Cross-module note* at the
> end); everything else in this document is P. Rohith's own work.

## Implemented files

- `src/pramana/analysis/ingestion.py`
  - Reads CSV/XLSX files.
  - Enforces file-size and row-count limits.
  - Converts common missing markers such as `?` and `NULL`.
  - Reports dtypes, missingness, duplicates, memory, unique counts, and schema.
- `src/pramana/analysis/cleaning.py`
  - Works on a copy of the dataframe.
  - Detects duplicates, missingness, numeric conversions, constant columns,
    near-constant columns, high-cardinality fields, identifier-like fields,
    inconsistent labels, and configured numeric-range violations.
  - Returns a Pydantic `CleaningReport` describing every mutation.
- `src/pramana/analysis/profiling.py`
  - Produces numeric and categorical descriptive profiles.
  - Classifies binary, ordinal-like, time-like, and identifier-like fields.
  - Computes exploratory Pearson/Spearman, t-test/ANOVA, and chi-square
    relationship evidence.
- `src/pramana/analysis/config.py`
  - Loads `configs/analysis.yaml`. The `schema_inference` and `hypotheses`
    sections are validated with `extra="forbid"` and no defaults, so a typo'd or
    missing cutoff fails at load. `ingestion`, `cleaning` and `benchmark` are
    ignored by this loader and stay free to evolve.
  - Refuses a verification-tier model for schema inference at load time, which
    makes `AGENTS.md` §2's cost/trust split structural rather than a convention.
- `src/pramana/analysis/schema_inference.py`
  - Classifies every column as numeric, categorical, ordinal, datetime, id-like
    or unknown, from the values. Column names only corroborate a decision the
    value statistics already support, so it works on NHANES `RIDAGEYR` and
    NFHS-5 `v024` alike.
  - Fails closed: below `min_confidence`, below `min_non_null`, constant, or
    unique-but-unnamed and the column is `UNKNOWN` and excluded from hypothesis
    generation. `describe_unusable()` reports every exclusion.
  - `SemanticRefiner` sees ambiguous columns only. The public entrypoint now wires
    local Ollama/Gemma when Langfuse and a run UUID are available; the low-level
    deterministic classifier remains available directly from `schema_inference`.
- `src/pramana/analysis/hypotheses/`
  - `base.py` — the strategy interface plus `emit()`, the single place a
    `CandidateInsight` is constructed. `emit()` raises if `analysis_evidence`
    ever carries a p-value, q-value or verdict.
  - `correlation.py`, `group_difference.py`, `trend.py` — the three strategies.
    Each pre-filters on the same statistic the gateway gates that claim type on
    (Spearman, eta²/Cliff's delta, Kendall tau-b).
  - `generation.py` — `analyse()`, the module front door: frame in,
    `(SchemaProfile, list[CandidateInsight])` out, capped at
    `max_candidates_per_run` so BH-FDR's family size stays sane.

Relationship evidence is not a verification verdict and is never presented as
causal proof. Downstream verification owns falsification and PASS/REJECT
decisions.

## Handoff contract (analysis -> verification)

Three details decide whether a candidate tests the sentence it states, and all
three are covered by tests:

| Detail | Rule | Why |
|---|---|---|
| `variables` order | `[x, y]`; grouping first for `group_difference`, time axis first for `trend` | The falsification templates unpack it positionally and group by `VAR_X` |
| `reference_group` | The higher-median level, named in the claim | The gate's Cliff's delta is signed and oriented by this field |
| Claim wording | Fixed hedged templates only | Clears the gateway's universal/causal screen by construction |

`claim_screen` is an optional hook on `generate_candidates`. The screened
vocabulary lives in `verification/admissibility.py`, and analysis does not import
verification, so orchestration (which imports both) can pass the real screen in
and have a refusal happen one step earlier.

## Tests

| File | Tests | Covers |
|---|---|---|
| `tests/unit/analysis/test_data_pipeline.py` | 4 | ingestion limits, non-destructive cleaning, profiling |
| `tests/unit/analysis/test_analysis_config.py` | 18 | strict loading, model-tier refusal, range checks |
| `tests/unit/analysis/test_schema_inference.py` | 36 | one test per role, fail-closed paths, the Gemma seam |
| `tests/unit/analysis/test_candidate_generation.py` | 38 | the `SCOPE_P_Rohith.md` §6 acceptance test, contract compliance, the cap |
| **Total** | **96** | |

The candidate-generation tests run on `tests/fixtures/frames.py`, the same toy
frame the gateway acceptance test uses, so both modules are provably testing the
same data. One test there imports `verification.admissibility.screen` — the only
cross-module import in this folder, and deliberate: a claim template that trips
the screened vocabulary should fail in this suite rather than in a run.

Run them with:

```powershell
pytest tests/unit/analysis
```

Full suite as of 2026-09-18: **472 passed**, `ruff` and `mypy` clean.

## Module status

The table records component status; `SCOPE_P_Rohith.md` §4 gives the build order.

| Step | Component | State |
|---|---|---|
| 6 | `prioritization.py` — per-strategy quotas, protecting planted demo signals | **not started.** `generation.py` applies only the blunt `max_candidates_per_run` cap |
| 7 | `benchmark/curation.py`, `benchmark/contamination.py` — the 40-dataset benchmark | not started |
| 8 | `benchmark/demo_dataset.py` — demo subset + seeded false-correlation injection | not started |
| — | A Gemma client behind `SemanticRefiner` | implemented; live activation requires local Gemma and Langfuse credentials |

## Cross-module note

`src/pramana/analysis/` belongs to P. Rohith (`OWNERSHIP.md`). Schema inference
and `CandidateInsight` generation were built by P.P. Satya Karthikeya by team
agreement, recorded in the two commit messages that introduced them, and are
pending Rohith's review (`AGENTS.md` §8.10). Points worth his attention are
listed in the PR description; the substantive ones are the `min_abs_correlation`
pre-filter's interaction with the demo's injected false correlation, and the
`use_llm_for_ambiguous_only: false` branch, which now explicitly disables refinement.

## Local Gemma setup (14 October 2026)

This feature is independent of the 40-dataset benchmark. `analysis/gemma.py`
implements `SemanticRefiner` using the already-declared Ollama dependency and
structured JSON. `schema_inference.gemma` in `configs/analysis.yaml` defines the
model tag, local server, timeout, generation seed, temperature, output budget,
sample limits and maximum ambiguous columns handled in each inference pass.
`GEMMA_MODEL` and `GEMMA_BASE_URL` may override the tag and endpoint, but only local
Gemma models/endpoints are accepted; there is no Qwen, cloud, or DeepSeek fallback.

Every actual request starts a Langfuse generation under its run UUID. The native
graph's public analysis import inherits the UUID already bound by orchestration;
the optional handlers pass their request's run UUID explicitly. Standalone callers
can pass `run_id` to `analyse` or the public `infer_schema`. The deterministic
low-level `schema_inference.infer_schema` does not automatically call a model.

Missing tracing, disabled refinement, malformed responses, transport failure,
insufficient semantic confidence and value-incompatible roles all leave the column
unknown. Setting `use_llm_for_ambiguous_only: false` explicitly disables refinement;
it never lets the model overrule confident heuristics. Constant/thin columns are
not offered to the model. Refined datetime/ordinal roles receive the appropriate
time-axis metadata, and refined categorical/ordinal roles receive their levels.

Raw sample values go to local Ollama only. Langfuse receives column metadata with
the levels array omitted, configured model/seed and the structured decision, not
the raw sample array. Column classification is still a proposal-side operation;
it cannot create a verdict or write memory.

### Activation

1. Install the existing analysis requirements and run `ollama pull gemma2:2b`.
2. Ask the team for the Langfuse host and project public/secret keys. Put them in
   the ignored `.env` using `.env.example`, or set process environment variables.
   Do not paste or commit keys. Existing Docker `env_file` loading already supplies
   them to services. For other entrypoints, load `.env` before running the pipeline.
3. Run `.venv/Scripts/python.exe scripts/check_gemma.py`. This script loads the local
   `.env`, checks tracing credentials and authentication, and classifies synthetic
   column data with a fresh run UUID. It never prints secrets or stores dataset files.

Automated tests use fake Ollama and Langfuse clients. A live backend run cannot be
claimed until valid Langfuse credentials and the configured model are available.

## Data policy

Raw datasets and generated local artifacts are not copied into this repository.
Run the functions against a local input path and keep experiment outputs outside
Git or in the repository's ignored data/artifact locations.
