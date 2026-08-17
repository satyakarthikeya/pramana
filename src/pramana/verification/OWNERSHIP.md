# OWNERSHIP — `src/pramana/verification/`

**Owner:** P.P. Satya Karthikeya (CB.AI.U4AID23128)
**Module:** Verification & Evaluation
**Scope file:** `SCOPE.md`

## What lives here

The verification gateway — falsification code generation, sandboxed execution, the vetted
statistics library, BH-FDR correction, evidence scoring, verdicts + proof objects, and the
memory guard. This is the core novelty of PRAMANA, not a support module.

| Path | Component | Build order (SCOPE.md §4) |
|---|---|---|
| `stats/` | permutation, bootstrap, effect sizes — the trust anchor | 2 |
| `fdr.py` | Benjamini-Hochberg → q-values | 3 |
| `evidence.py` | deterministic evidence score | 4 |
| `executor/` | sandboxed runner + import/timeout policy | 5 |
| `falsification/` | DeepSeek V4 code generation + prompts | 6 |
| `gateway.py` | orchestrator wiring it all together | 7 |
| `memory_guard.py` | the single PASS-check every write flows through | 8 |
| `config.py` | loads `configs/verification.yaml` | — |

## Who may edit

Satya Karthikeya only. Anyone else: open an issue, don't edit.

## Who may import, and what

- **Everyone** may import `pramana.contracts` (defined here's sibling package) freely.
- `pramana.memory` imports `memory_guard` — that is the sanctioned integration point.
- `pramana.orchestration` imports `gateway` as a graph node.
- Nothing here imports another member's module. The gateway must be testable alone.

## Hard rules for anything in this folder

1. p-values come from **executed** code, never from LLM reasoning (`AGENTS.md` §3.1).
2. BH-FDR is applied **once per run** across all hypotheses, then verdicts are issued.
3. Thresholds and seeds live in `configs/verification.yaml`, never inline.
4. Crash, timeout, or malformed output ⇒ **fail-closed**. There is no code path from a
   failed execution to `PASS`.
5. Every verdict emits a **complete** proof object. No partial ones.
6. LLM-generated code is untrusted input — whitelist, timeout, no network, no file writes
   outside a temp dir.

## Definition of done

Type hints, pydantic-validated I/O, pytest known-answer statistical tests
(planted null → high p, planted effect → low p), structured logs carrying `insight_id`,
and a test proving fail-closed behaviour.
