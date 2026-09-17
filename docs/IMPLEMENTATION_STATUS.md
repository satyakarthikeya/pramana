# IMPLEMENTATION_STATUS.md — verification gateway, current state

> Scope: `src/pramana/verification/`, `src/pramana/contracts/`, `tests/`, and
> `configs/verification.yaml` (Satya Karthikeya's module). Other members' folders are
> not tracked here. Last updated 2026-09-17, after the post-review bugfix pass.

## Headline

**Phases 1–5 of `SCOPE.md` §4 are implemented and test-green.** The deterministic
core — contracts, statistics library, BH-FDR, evidence gate, sandboxed executor — plus
the config loader, admissibility screen and the deterministic template generator all
exist, are covered by the pre-written suite, and pass. Phases 6–8 (LLM generator path,
gateway orchestrator, memory guard) are still stubs; their test files fail at
collection with `ImportError`, which is the expected TDD state for a phase not yet
built (see `pramana-phase-discipline`: forward-referencing tests stay red, never
patched).

## Phase-by-phase

| Phase | Component | File(s) | State |
|---|---|---|---|
| 1 | Contracts | `contracts/enums.py`, `candidate_insight.py`, `proof_object.py` | **done** — frozen models; PASS ⟺ SUPPORTED, null-iff-untested, score-only-on-finding enforced by validators |
| 2 | Statistics library | `verification/stats/permutation.py`, `bootstrap.py`, `effect_size.py`, `provenance.py` | **done** — add-one permutation p, percentile bootstrap, five gating + four reported effect metrics, HMAC stamp |
| 3 | BH-FDR | `verification/fdr.py` | **done** — pinned against `statsmodels` incl. ties |
| 4 | Evidence gate + score | `verification/evidence.py` | **done** — hard conjunction gate, geometric-mean score for ranking only |
| 5 | Sandboxed executor | `verification/executor/policy.py`, `runner.py` | **done** — static import policy, subprocess + timeout, payload validation, stamp verification |
| — | Config loader | `verification/config.py`, `configs/verification.yaml` | **done** — no defaults, `extra="forbid"`, forbidden-library and floor-below-alpha validators |
| — | Admissibility screen | `verification/admissibility.py` | **done** |
| 6 | Falsification generator | `falsification/templates.py`, `generator.py`, `prompts.py` | **partial** — deterministic template path exists and is what the executor tests run; `get_generator` / LLM path not built |
| 7 | Gateway orchestrator | `verification/gateway.py` | **stub** |
| 8 | Memory guard | `verification/memory_guard.py` | **stub** |
| 9 | Langfuse tracing | — | not started |

## Suite status (2026-09-17)

```
pytest tests/unit --ignore=tests/unit/verification/test_falsification.py \
                  --ignore=tests/unit/verification/test_gateway.py \
                  --ignore=tests/unit/verification/test_memory_guard.py
```

All green. `test_falsification.py`, `test_gateway.py`, `test_memory_guard.py` and
`tests/integration/test_gateway_e2e.py` fail at collection (`ImportError` on names
that Phases 6–8 will define). That is the intended state.

## Bugfix pass applied (2026-09-17)

A code review of Phases 1–5 found one fail-open path and several hardening gaps.
All were closed in a single commit, with tests:

1. **Non-finite effect size no longer PASSes.** `gated_effect < band.min` is False for
   NaN, so a NaN effect skipped the NEGLIGIBLE check and `effect_leg` clamped it to
   1.0 — a false SUPPORTED. The runner now refuses any non-finite `effect_size`, and
   `evaluate_gate` raises on one (second lock).
2. **`effect_size` is under the stamp.** The HMAC covers `statistic`, not
   `effect_size`; in every vetted test the two are the same number, so the runner now
   requires `effect_size == statistic`.
3. **`n_permutations` / `seed` must match the run's config.** A genuinely stamped
   result from an under-powered or privately seeded test is refused.
4. **The provenance module is unreachable from generated code** — as a module path, an
   imported name, or an attribute on an imported module. Private (`_`-prefixed) names
   of the stats package are likewise refused. Reading `result.provenance` (the stamp
   string on a vetted result) stays allowed, because the templates need it.
5. **`getattr`, `setattr`, `delattr`, `type`** added to `FORBIDDEN_BUILTINS`.
6. **Subprocess environment** now passes through `SYSTEMROOT`, `PATH`,
   `LD_LIBRARY_PATH` and `PYTHONHOME` (only when set) so the interpreter can boot on
   every platform; nothing else crosses.
7. **`p_value_floor >= alpha` is refused at config load**, not at scoring time.

## Known gaps carried deliberately

- **`RLIMIT_AS` under Docker on Linux — needs verification inside the Docker image.**
  The runner caps address space at `max_memory_mb` on POSIX. OpenBLAS reserves large
  virtual ranges at import, and a 1 GB address-space cap is known to break
  `import numpy` in some builds. This cannot be exercised on the Windows dev machine
  (the cap is advisory there; the container is the real enforcement). Run one
  template through the executor inside the image before relying on the cap.
- **`MIN_OBSERVATIONS` is both hardcoded (3, in `stats/`) and configured (20, in
  `verification.yaml`).** The stats floor is a "can this be computed at all" guard;
  the configured one is the gate's "is this worth concluding from" floor. Phase 6
  must make sure every template caller uses the configured value.
- **`mypy` does not currently run**: the venv's numpy stubs use `type` statements that
  need `python_version = "3.12"`, and `pyproject.toml` pins 3.11. Config decision, not
  a code defect.
- The effect-size bands are still PROVISIONAL (`docs/OPEN_ISSUES.md` §11), Cramér's V
  is banded but unreachable (§10), and `bootstrap_ci` is not wired to any template.

## Running it

```
cd pramana
.venv\Scripts\activate
pytest tests/unit -q --ignore=tests/unit/verification/test_falsification.py --ignore=tests/unit/verification/test_gateway.py --ignore=tests/unit/verification/test_memory_guard.py
ruff check .
```
