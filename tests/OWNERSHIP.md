# OWNERSHIP — `tests/`

Test folders mirror `src/` ownership. You write the tests for your own module.

| Path | Owner |
|---|---|
| `unit/contracts/` | P.P. Satya Karthikeya |
| `unit/verification/` | P.P. Satya Karthikeya |
| `unit/analysis/` | P. Rohith |
| `unit/orchestration/` | B. Karthikeya |
| `unit/memory/` | M. Karthik Reddy |
| `integration/` | B. Karthikeya (owns the harness); everyone contributes cases |
| `fixtures/` | shared — toy dataframes with planted signals |
| `conftest.py` | shared |

## Tests that must never be deleted or skipped

These encode the project's core promise. If one fails, the code is wrong — not the test.

1. **Known-answer statistical tests** (`unit/verification/`): planted null → high p;
   planted strong effect → low p. The stats library is the trust anchor.
2. **BH-FDR reference test**: our q-values match statsmodels/scipy output.
3. **Fail-closed test**: a crashed or timed-out execution can never yield `PASS`.
4. **No-bypass import test** (`unit/memory/`): no file outside `src/pramana/memory/`
   imports `chromadb`.
5. **Guard test**: storing a `REJECT`ed proof object raises and writes nothing.
6. **Graph integration test** (`integration/`): toy dataframe through the full graph —
   every candidate insight has a proof object, no REJECT reaches memory.

## Shared fixtures

`fixtures/` holds the toy dataset used across modules: one strong planted relationship,
one pure-noise pair, one group difference. Both the analysis acceptance test and the
gateway acceptance test run against it, so the two modules are provably testing the same
thing.

## Rules

- Pytest, deterministic, seeded. A flaky statistical test is a broken statistical test.
- Don't loosen another member's assertions to make your change pass — talk to them.
