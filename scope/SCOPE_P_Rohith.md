# SCOPE_P_Rohith.md — Work scope: Data Analysis Module

> Owner: P. Rohith (CB.AI.U4AID23123)
> This file defines what the coding agent is building RIGHT NOW for this member.
> Context: `PROJECT.md`. Rules: `AGENTS.md`. Other members have their own SCOPE_*.md files.

## 1. What we are building

The **data analysis module**: everything from raw uploaded dataset to a list of
well-formed candidate insights handed to the verification gateway. This is the
"proposer" side of PRAMANA — it is ALLOWED to over-propose plausible hypotheses,
because the gateway downstream filters them. It must never self-certify an insight.

## 2. In scope

| # | Component | Description |
|---|---|---|
| 1 | Ingestion pipeline | Accept CSV/XLSX upload, size/row limits, basic validation, load to pandas with stable dtypes |
| 2 | Schema inference (Gemma) | Column type/semantic classification (numeric, categorical, ordinal, datetime, ID-like), leveraging local Gemma for naming/semantics; deterministic heuristics first, LLM only for ambiguity |
| 3 | Cleaning & profiling | Missing-value handling, outlier flagging, dedup, per-column profile (distribution stats), cleaning report so downstream steps know what was changed |
| 4 | Hypothesis generation | Strategies to propose candidate insights: pairwise correlation scans, group-difference candidates (categorical × numeric), trend candidates (datetime × numeric). Each emitted as a CandidateInsight (schema in PROJECT.md §5) with `analysis_evidence` = the raw exploratory stat only |
| 5 | Candidate prioritization | Rank/cap candidates per run (config-driven max N) so the gateway isn't flooded — BH-FDR behaves better with a sane hypothesis count |
| 6 | Evaluation dataset curation | Build the 40-dataset benchmark: source from NHANES/NFHS-5/other open data, contamination screening (exclude Iris/Titanic/famous datasets), and prepare the DEMO dataset with one injected false correlation + real published relationships |

## 3. Out of scope (do NOT touch)

- Any verification logic: falsification tests, p-values as VERDICTS, BH-FDR, evidence scoring (Satya Karthikeya's module). The exploratory stats this module computes are hints, never verdicts.
- LangGraph graph structure, Celery/Redis plumbing, Docker (B. Karthikeya's module)
- ChromaDB memory framework, deployment, dashboard (Karthik Reddy's module)
- MIMIC-IV in any form (license conflict — see AGENTS.md §6)

## 4. Build order (first → last)

1. **Ingestion + dtype-stable loading** — small, deterministic, testable; everything depends on a clean dataframe.
2. **Deterministic schema inference heuristics** — type/semantic classification without LLM; add the Gemma call only where heuristics are ambiguous.
3. **Cleaning & profiling with a cleaning report** — every mutation of the data is logged; the gateway needs to test the SAME dataframe the candidates came from.
4. **CandidateInsight emission** — implement the Pydantic contract; a hand-written dummy generator first so the gateway team can integrate against it immediately.
5. **Hypothesis generation strategies** — correlation scan → group differences → trends, each behind a common interface; config-driven caps.
6. **Prioritization/ranking** — cap candidates per run; ensure planted-demo-style signals aren't accidentally filtered out before the gateway sees them.
7. **Benchmark curation** — 40 datasets, contamination screening checklist documented per dataset (needed for the report).
8. **Demo dataset construction** — NHANES/NFHS-5 subset (~500–2,000 rows, 8–15 cols) + injection script for the false correlation (seeded, reproducible).

Rationale: contract-first (step 4 early) unblocks the verification member; benchmark/demo
work is parallelizable and report-critical, so it's explicit scope, not an afterthought.

## 5. Definition of done (per component)

- Type-hinted, Pydantic-validated outputs; CandidateInsight contract imported, not redefined
- Pytest coverage: known dataframes → expected schema classification, expected candidate sets
- Cleaning is reproducible (seeded) and fully logged in the cleaning report
- No component ever labels an insight verified/true — proposer role only
- Gemma used only for cheap semantic tasks; all LLM calls traced in Langfuse

## 6. Acceptance test (end-to-end for this module)

Feed a toy dataframe with one strong planted relationship, one pure-noise pair, and one
group difference. Expected: ingestion+cleaning preserve the planted structure, schema
inference classifies all columns correctly, hypothesis generation emits CandidateInsights
covering all three (plus extras is fine), all valid against the contract, none marked as
verified, and the demo injection script reproducibly plants a false correlation detectable
by the gateway.
