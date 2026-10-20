# Forty-extract source handoff

Owner: P. Rohith. Built 18 October 2026. Rohith authorized expansion while
Satya's pilot evaluation is pending. The first ten source definitions are unchanged.
This branch depends on pilot PR #16; merge #16 first, then review this expansion.

## Purpose

The pilot was the first ten extracts, intended to catch cleaning and integration
problems before producing forty. It is a development checkpoint, not a separate
research result. This release completes the source collection in PROJECT.md section 6.
Satya still owns independent column shuffling, seeded relationship injection,
truth labels, the four-condition evaluation harness and accuracy measurements.
No claimed statistical result or verification verdict is produced by this builder.

## Actual build

- 40 real NHANES extracts, 58,000 total rows, 1,000 or 3,000 rows each, 14-21 columns.
- 53,092 missing cells retained, including 189 documented nonresponse replacements.
- Nine ordered-cycle extracts use original SDDSRVYR values over 2013-2018.
- No column shuffle, injection, imputation or extra missing-value row removal.
- All 40 have distinct cycle/module/fixed-column definitions, rather than duplicate resamples.
- Extracts share participants and source modules. The overlap matrix in the build
  report must inform Satya's evaluation splits and uncertainty estimates; these
  are not forty independent population samples. Pooled weights remain unadjusted.
- Only public-use NHANES; no NFHS/DHS credential requirement and no restricted records.

## Reproduce on a teammate's machine

```powershell
python scripts/build_benchmark_pilot.py --plan configs/benchmark_40.yaml --summary artifacts/benchmark_40_build.json
python scripts/build_benchmark_pilot.py --plan configs/benchmark_40.yaml --check-only --offline
```

The existing CLI accepts either the ten- or forty-extract plan. Source locks are
selected from the plan filename: benchmark_40_sources.json for this release.
Use --offline to rebuild from cached official files. Use the same pandas version
recorded in the report for byte-identical CSV reproduction.

Outputs: data/benchmark/extracts/<dataset_id>/extract.csv and metadata.json.
Raw files and extracts stay gitignored. Teammates get the code, full plan, source
checksums, aggregate build report and per-extract metadata through GitHub, and run
the command above to obtain the real files locally.

See [build audit](benchmark_40_build.json), [metadata](benchmark_40_metadata.json),
[fixed plan](../configs/benchmark_40.yaml), and [source lock](../configs/benchmark_40_sources.json).
The metadata-aware schema helper and unchanged responsibility split are described
in [the original handoff](ROHITH_HANDOFF.md).

## Extract inventory

| Dataset ID | Rows | Columns | Coverage |
|---|---:|---:|---|
| `nhanes_2017_bmx_01` | 1000 | 15 | numeric_pairs |
| `nhanes_2017_bpx_02` | 1000 | 17 | numeric_pairs |
| `nhanes_2017_biopro_03` | 1000 | 19 | numeric_pairs |
| `nhanes_2017_diq_ghb_04` | 1000 | 16 | group_differences |
| `nhanes_2017_smq_bmx_05` | 1000 | 17 | group_differences |
| `nhanes_2017_paq_bmx_06` | 1000 | 19 | group_differences |
| `nhanes_2013_2018_bmx_trend_07` | 3000 | 15 | trends |
| `nhanes_2013_2018_bpx_trend_08` | 3000 | 17 | trends |
| `nhanes_2013_2018_ghb_bmx_trend_09` | 3000 | 14 | trends |
| `nhanes_2017_slq_bmx_10` | 1000 | 17 | mixed |
| `nhanes_2013_bmx_11` | 1000 | 15 | numeric_pairs |
| `nhanes_2013_bpx_12` | 1000 | 17 | numeric_pairs |
| `nhanes_2013_biopro_13` | 1000 | 19 | numeric_pairs |
| `nhanes_2013_diq_ghb_14` | 1000 | 16 | group_differences |
| `nhanes_2013_smq_bmx_15` | 1000 | 17 | group_differences |
| `nhanes_2013_paq_bmx_16` | 1000 | 19 | group_differences |
| `nhanes_2015_bmx_17` | 1000 | 15 | numeric_pairs |
| `nhanes_2015_bpx_18` | 1000 | 17 | numeric_pairs |
| `nhanes_2015_biopro_19` | 1000 | 19 | numeric_pairs |
| `nhanes_2015_diq_ghb_20` | 1000 | 16 | group_differences |
| `nhanes_2015_smq_bmx_21` | 1000 | 17 | group_differences |
| `nhanes_2015_paq_bmx_22` | 1000 | 19 | group_differences |
| `nhanes_2013_bmx_bpx_23` | 1000 | 21 | numeric_pairs |
| `nhanes_2015_bmx_bpx_24` | 1000 | 21 | numeric_pairs |
| `nhanes_2017_bmx_bpx_25` | 1000 | 21 | numeric_pairs |
| `nhanes_2013_ghb_biopro_26` | 1000 | 20 | numeric_pairs |
| `nhanes_2015_ghb_biopro_27` | 1000 | 20 | numeric_pairs |
| `nhanes_2017_ghb_biopro_28` | 1000 | 20 | numeric_pairs |
| `nhanes_2013_diq_bmx_29` | 1000 | 19 | group_differences |
| `nhanes_2015_diq_bmx_30` | 1000 | 19 | group_differences |
| `nhanes_2017_diq_bmx_31` | 1000 | 19 | group_differences |
| `nhanes_2013_smq_bpx_32` | 1000 | 21 | group_differences |
| `nhanes_2015_smq_bpx_33` | 1000 | 21 | group_differences |
| `nhanes_2017_smq_bpx_34` | 1000 | 21 | group_differences |
| `nhanes_2013_2018_biopro_trend_35` | 3000 | 19 | trends |
| `nhanes_2013_2018_diq_ghb_trend_36` | 3000 | 16 | trends |
| `nhanes_2013_2018_smq_bmx_trend_37` | 3000 | 17 | trends |
| `nhanes_2013_2018_paq_bmx_trend_38` | 3000 | 19 | trends |
| `nhanes_2013_2018_bmx_bpx_trend_39` | 3000 | 21 | trends |
| `nhanes_2013_2018_ghb_biopro_trend_40` | 3000 | 20 | trends |

## Langfuse activation

Validation: 110 analysis tests and 505 full-suite tests passed; repository ruff
and analysis/CLI mypy checks passed. The first full run hit an existing workflow
deadline while builds ran concurrently; an isolated full rerun passed without
test or timeout changes. Build, offline rebuild and check-only audit reports match;
the original ten source CSV/cohort hashes remain unchanged.

Langfuse records model calls under each run ID so the team can inspect which
model was called, its output, and failures. It does not decide correctness.
Ask the team's Langfuse project owner/admin for access and a project public key,
secret key and host URL. Satya can identify the owner; repo ownership does not
establish who has a Langfuse account. If no project exists, the team must create
one first. Project credentials go only into the ignored local .env fields
LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_HOST.

Official instructions: https://langfuse.com/faq/all/where-are-langfuse-api-keys
and https://langfuse.com/docs/administration/rbac . No credentials are needed for
this deterministic benchmark builder. Once configured, the Gemma PR #15 provides
python scripts/check_gemma.py for the live traced check. That check is still pending.
