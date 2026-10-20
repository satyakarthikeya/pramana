# Rohith's contribution and team handoff

Snapshot: 18 October 2026. Owner: P. Rohith, CB.AI.U4AID23123.

## Where the team can review the work

| Work | Repository location | Status at this snapshot |
|---|---|---|
| Ingestion, cleaning report, profiling | [PR #6](https://github.com/satyakarthikeya/pramana/pull/6) | Merged |
| Candidate selection with strategy reservations | [PR #13](https://github.com/satyakarthikeya/pramana/pull/13), branch `feat/rohith/candidate-selection` | Pushed, open for review |
| Worker-readable cleaned artifact handoff | [PR #14](https://github.com/satyakarthikeya/pramana/pull/14), branch `fix/rohith/worker-dataset-reference` | Pushed, open for review |
| Traced local Gemma schema refinement | [PR #15](https://github.com/satyakarthikeya/pramana/pull/15), branch `feat/rohith/gemma-schema-refiner` | Pushed, open for review |
| Approved ten-extract NHANES pilot | [Branch `feat/rohith/benchmark-pilot`](https://github.com/satyakarthikeya/pramana/tree/feat/rohith/benchmark-pilot) | This contribution; review before merge |

Each branch contains one workstream and starts from the team main baseline. The
three earlier PRs remain available, independently reviewable and unmerged. This
pilot does not silently copy their implementations into a combined branch. A team
reviewer must merge approved PRs through GitHub; no direct main commits are needed.

The old `feat/rohith/analysis-pipeline` branch is also preserved remotely. Its
alternative hypothesis/public-handler interfaces were superseded by the merged
implementation. Its earlier diabetes demo is not used for this approved NHANES pilot.

## Approved pilot and responsibility split

Satya's ten-source approval was relayed by Rohith on 18 October 2026. This implements
the approved **pilot of ten**, not a claim that the final 40-dataset evaluation is
finished. The source plan is [benchmark_pilot.yaml](../configs/benchmark_pilot.yaml).

| Dataset ID | Source modules | Cycle(s) | Rows | Columns | Intended coverage |
|---|---|---|---:|---:|---|
| `nhanes_2017_bmx_01` | DEMO + BMX | 2017–18 | 1,000 | 15 | Numeric pairs |
| `nhanes_2017_bpx_02` | DEMO + BPX | 2017–18 | 1,000 | 17 | Numeric pairs |
| `nhanes_2017_biopro_03` | DEMO + BIOPRO | 2017–18 | 1,000 | 19 | Numeric pairs |
| `nhanes_2017_diq_ghb_04` | DEMO + DIQ + GHB | 2017–18 | 1,000 | 16 | Group differences |
| `nhanes_2017_smq_bmx_05` | DEMO + SMQ + BMX | 2017–18 | 1,000 | 17 | Group differences |
| `nhanes_2017_paq_bmx_06` | DEMO + PAQ + BMX | 2017–18 | 1,000 | 19 | Group differences |
| `nhanes_2013_2018_bmx_trend_07` | DEMO + BMX | 2013–14, 2015–16, 2017–18 | 3,000 | 15 | Ordered cycle trends |
| `nhanes_2013_2018_bpx_trend_08` | DEMO + BPX | Same three cycles | 3,000 | 17 | Ordered cycle trends |
| `nhanes_2013_2018_ghb_bmx_trend_09` | DEMO + GHB + BMX | Same three cycles | 3,000 | 14 | Ordered cycle trends |
| `nhanes_2017_slq_bmx_10` | DEMO + SLQ + BMX | 2017–18 | 1,000 | 17 | Mixed |

All extracts use adults aged 20+. Whole records are sampled with the configured
seed plus the cycle's start year, then sorted by cycle and SEQN. This selects the
approved bounded subsets without breaking real pairings or missingness patterns.

- **Rohith supplies:** original unshuffled extracts, metadata, codebook-driven
  nonresponse handling, provenance/contamination screening and rebuild instructions.
- **Satya supplies:** column shuffling, relationship injection, truth labels,
  injection seed schedule, scoring and evaluation harness. Those are not implemented
  or run by the source-extract builder.
- Scale to 40 after the pilot works with Satya's harness and the next sources are
  agreed. NFHS-5 remains excluded until project-authorized DHS access/terms are settled.

## Rebuild the actual data on another team member's machine

Raw records and SAS files are deliberately **not committed** (`AGENTS.md` section 6).
The code, fixed column plan, public source checksums, actual metadata and aggregate
build report are committed so teammates can reproduce the handoff.

After checking out this branch or its reviewed merge and installing the normal
analysis requirements:

```powershell
python scripts/build_benchmark_pilot.py --summary artifacts/pilot_build.json
```

This downloads the required official CDC files into `data/raw/nhanes/` and creates:

```text
data/benchmark/extracts/<dataset_id>/
    extract.csv
    metadata.json
```

The CSVs are UTF-8 with headers and original NHANES column names. The metadata
contains source/cycles, filters and row sampling, UTC extraction date, actual row
and column counts, documented semantic dtype, missing count/percentage per column,
time axis, weight/ID/design flags, nonresponse codes/replacement counts, source URLs
and hashes, screening notes, original cohort hash and extract hash.

For cached source data and existing handoffs:

```powershell
python scripts/build_benchmark_pilot.py --offline --summary artifacts/pilot_rebuild.json
python scripts/build_benchmark_pilot.py --check-only --offline
```

The reviewed [source lock](../configs/benchmark_pilot_sources.json) records byte
hashes for every SAS file and codebook. A changed cached source is refused rather
than silently accepted. Missing cached files in offline mode fail clearly. Source
updates require review of the lock. Reproduction was checked with the pandas version
recorded in the build report; different library versions may serialize floats differently.

The extraction timestamp can change on rebuild. CSV/cohort content hashes, selected
records, missingness and aggregate summary reproduce under the same plan, sources
and software. No Langfuse credentials or LLM calls are required for building the pilot.

## What was checked on the real pilot

See [actual build report](benchmark_pilot_build.json) and
[full metadata report](benchmark_pilot_metadata.json). These contain aggregate audit
information and schema/codebook metadata, not participant records.

- 10 valid handoffs; 16,000 rows total; 14–19 columns per extract.
- 9,120 missing cells retained, including 37 documented nonresponse replacements.
- Blank only values explicitly described as Refused/Don't know for that variable
  in that cycle's official frequency table. Do not globally replace 7, 9, 7777 or 9999:
  such numbers can be valid values in a different column.
- Remove exact duplicate rows; refuse conflicting duplicate respondent keys rather
  than choosing one. Secondary modules are left joins, not complete-case filters.
- No imputation, outlier deletion, numeric-range clipping, additional missing-value
  row drops, renaming, independent column shuffle or relationship injection.
- Preserve original survey weights. They are not adjusted into pooled population
  weights. This is a benchmark source handoff, not a survey-population analysis.
- Participant overlap between extracts is measured in the build report. These are
  not ten independent population samples; evaluation splits/uncertainty must account
  for the source/participant overlap.

## Using the original release-cycle axis and survey metadata

`SDDSRVYR` is the genuine NHANES release-cycle code. The three pooled extracts
retain its original values and designate it as the ordered axis. They are repeated
cross-sections, not within-person longitudinal follow-up.

Automatic inference on a bare CSV does not recognize every coded column name.
Satya's harness can use the analysis-owned metadata helper:

```python
from pathlib import Path
from pramana.analysis.benchmark.curation import load_extract, schema_for_extract
from pramana.analysis.config import load_config
from pramana.analysis.hypotheses.generation import generate_candidates

directory = Path("data/benchmark/extracts/nhanes_2013_2018_bmx_trend_07")
frame, metadata = load_extract(directory)
schema = schema_for_extract(frame, metadata)
candidates = generate_candidates(
    frame, schema, load_config().hypotheses,
    dataset_ref=str((directory / "extract.csv").resolve()),
)
```

The helper marks the approved axis explicitly and excludes IDs, survey weights and
design fields from candidate generation. It does not rename or modify data. After
Satya builds an injected evaluation frame, he must recompute its metadata/profile
and use a reference to that exact new frame, not reuse the original extract's hash.
The full batch still goes through verification once. Candidate counts in the build
report are exploratory proposals, not verified findings or evaluation results.

No extract was chosen to force an observed native trend. Structural axis eligibility
is checked; the known benchmark relationships are Satya's next stage.

## Source and contamination notes

Only direct official public-use NHANES components are accepted by this pilot's
screen. No packaged Iris/Titanic/Wine/Boston/mtcars/diabetes ML dataset, MIMIC,
PhysioNet or repackaged third-party benchmark is used. A diabetes-questionnaire
module from NHANES is not the excluded packaged diabetes ML dataset. Screening
cannot prove that NHANES never appeared in a model's training corpus.

Source references: [CDC public NHANES access](https://www.cdc.gov/nchs/nhanes/about/index.html),
[CDC materials policy](https://www.cdc.gov/other/agencymaterials.html), and each
component's official codebook URL in the metadata. Public-use records only; no
restricted files or re-identification. Actual per-component provenance is recorded
in every local metadata file and the committed metadata report.

## Outstanding team activation and review

Validation for this pilot contribution:

- `python -m pytest tests/unit/analysis -q -o addopts=--strict-markers --tb=short`:
  **109 passed**, including 9 new pilot tests.
- `python -m pytest -q -o addopts=--strict-markers --tb=short`: **504 passed**;
  5 pre-existing TestType enum collection warnings.
- `python -m ruff check .`: passed.
- `python -m mypy src/pramana/analysis scripts/build_benchmark_pilot.py --python-version 3.13`:
  passed, 19 source files. The override matches the installed interpreter and avoids
  the previously documented numpy-stub issue with the project's 3.11 pin.
- Real build, cached rebuild and check-only validation: all ten handoffs valid;
  aggregate summary and CSV/cohort hashes reproduced exactly.

These counts are for this branch's main baseline plus the pilot. They do not claim
that an unmerged combination of PRs #13–15 has been integration-tested here.

All earlier contribution code is pushed in the linked PRs. Gemma 2 2B is installed
on Rohith's machine, but a live traced model run still needs the team's Langfuse
project credentials; do not paste or commit keys. After configuring the ignored
`.env`, the Gemma PR provides `python scripts/check_gemma.py` to check activation.

The worker-handoff PR has automated process/loader tests; a deployed Celery/Docker
run remains a team integration check. These activation checks and the final
40-dataset evaluation are not claimed complete by this pilot contribution.
