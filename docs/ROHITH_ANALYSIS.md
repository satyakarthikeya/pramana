# P. Rohith — Data Analysis Module

This module owns the proposer-side data path:

```text
CSV/XLSX input
  -> bounded ingestion and metadata
  -> conservative cleaning and audit report
  -> descriptive profiling and exploratory relationship evidence
  -> future CandidateInsight generation
  -> benchmark source manifest and contamination screening
```

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

Relationship evidence is not a verification verdict and is never presented as
causal proof. Downstream verification owns falsification and PASS/REJECT
decisions.

## Benchmark curation

`src/pramana/analysis/benchmark/curation.py` builds a Pydantic manifest of 40
source records without copying raw data into Git. Each record includes its
source family, official source URL, reproducibility seed, and an auditable
contamination-screening result. `screen_source` rejects famous benchmark
datasets and forbidden MIMIC/PhysioNet sources before a manifest can be marked
ready.

The manifest is metadata only. Local benchmark files must live under the
gitignored `data/benchmark/` directory and can be checked with
`validate_local_files`.

## Demo dataset

`build_demo_from_diabetes` accepts the local `demodataset/diabetic_data.csv`
source directory and creates a reproducible 500–2,000 row demo CSV under the
ignored `data/demo/` directory. It preserves hospital variables such as
length of stay, lab procedures, medication count, utilization, demographics,
and readmission status. It also adds one independently shuffled
`injected_false_signal` column so the gateway receives a known noise
relationship without modifying the source dataset.

## Tests

Focused coverage is in:

`tests/unit/analysis/test_data_pipeline.py`

It covers missing-marker ingestion, input limits, non-destructive cleaning,
quality diagnostics, descriptive statistics, and relationship evidence.

Run it with:

```powershell
pytest tests/unit/analysis/test_data_pipeline.py
```

## Data policy

Raw datasets and generated local artifacts are not copied into this repository.
Run the functions against a local input path and keep experiment outputs outside
Git or in the repository's ignored data/artifact locations.
