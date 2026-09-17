# P. Rohith — Data Analysis Module

This module owns the proposer-side data path:

```text
CSV/XLSX input
  -> bounded ingestion and metadata
  -> conservative cleaning and audit report
  -> descriptive profiling and exploratory relationship evidence
  -> future CandidateInsight generation
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
