# OWNERSHIP — `src/pramana/analysis/`

**Owner:** P. Rohith (CB.AI.U4AID23123)
**Module:** Data Analysis
**Scope file:** `scope/SCOPE_P_Rohith.md`

## What lives here

Everything from a raw uploaded file to a list of well-formed `CandidateInsight`s, plus
the evaluation/benchmark dataset curation.

| Path | Component | Build order (SCOPE_P §4) |
|---|---|---|
| `ingestion.py` | CSV/XLSX load, limits, dtype stability | 1 |
| `schema_inference.py` | type/semantic classification (heuristics → Gemma) | 2 |
| `cleaning.py`, `profiling.py` | cleaning + profile + cleaning report | 3 |
| `hypotheses/` | correlation, group-difference, trend strategies | 4–5 |
| `prioritization.py` | rank/cap candidates per run | 6 |
| `benchmark/` | 40-dataset curation, contamination screen, demo dataset | 7–8 |

## The role this module plays

**Proposer, never judge.** It is allowed — encouraged — to over-propose plausible
hypotheses, because the gateway filters them downstream. The exploratory statistics
computed here are *hints* that go in `analysis_evidence`. They are never verdicts, never
"verified", never shown to the user as findings.

## Who may edit

P. Rohith only.

## Who may import, and what

- `orchestration` calls the public ingestion / hypothesis-generation entrypoints.
- `verification` does **not** import this package — it receives `CandidateInsight`
  objects and the dataframe reference, nothing more.

## Hard rules

1. Emit the `CandidateInsight` contract from `pramana.contracts` — imported, not redefined.
2. Cleaning is seeded and reproducible, and every mutation lands in the cleaning report —
   the gateway must test the *same* dataframe the candidates came from.
3. Gemma (local) for cheap semantic work only. Never DeepSeek. All calls traced.
4. **MIMIC-IV is forbidden** (`AGENTS.md` §6). NHANES / NFHS-5 / other open data only.
5. Benchmark excludes famous datasets (Iris, Titanic, …) — screening documented per
   dataset, because the report needs it.
6. Raw data never gets committed; it lives in the gitignored `data/`.

## Contract-first note

Ship a hand-written dummy candidate generator early (SCOPE_P §4 step 4) so the gateway
can integrate before real hypothesis generation is finished.
