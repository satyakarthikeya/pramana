# OWNERSHIP — `src/pramana/evaluation/`

**Owner:** P.P. Satya Karthikeya (CB.AI.U4AID23128)
**Module:** Verification & Evaluation (benchmarking half)
**Scope file:** `SCOPE.md`

## Status: later work item, not current scope

`SCOPE.md` §3 explicitly parks the ablation harness as a **separate** work item from the
gateway build. The folder exists so it isn't bolted on in the final week — it is not what
gets built right now.

## What will live here

The four-condition ablation over the 40-dataset benchmark (`PROJECT.md` §6):

| Condition | Setup |
|---|---|
| A | single LLM call, no agent loop |
| B | agent loop, no verification gate |
| C | agent loop + LLM critic (judges insights, no execution) |
| D | full PRAMANA (agent loop + execution-grounded gate) |

Plus precision metrics, the batch-vs-episode self-evolution comparison, and the result
tables for the report.

## Boundaries

- The benchmark **datasets** are curated by P. Rohith (`analysis/benchmark/`). This folder
  consumes them; it does not source or clean them.
- Running conditions uses the orchestration graph with modules swapped out — it does not
  fork its own pipeline.

## Reporting rule

n=40 gives thin statistical power. Results are framed as **directional trends**, and the
limitation is stated openly in the report rather than buried (`PROJECT.md` §6). Do not
write code, tables, or captions that imply more certainty than the design supports.
