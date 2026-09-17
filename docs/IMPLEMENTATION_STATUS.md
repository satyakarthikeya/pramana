# IMPLEMENTATION_STATUS.md — verification gateway, current state

> Scope: `src/pramana/verification/`, `src/pramana/contracts/`, `tests/`, and
> `configs/verification.yaml` (Satya Karthikeya's module). Other members' folders are
> not tracked here. Last updated 2026-09-17, after Phase 9 (final verification).

## Headline

**All nine phases of `SCOPE.md` §4 are implemented and the full suite is green: 322
passed, zero failures, zero collection errors.** The gateway runs end to end. The
`SCOPE.md` §6 acceptance test passes against real code at every layer — real
admissibility screen, real template generator, real subprocess executor, real BH-FDR,
real evidence gate, real memory guard, and no mocks anywhere in the statistical path.

The product claim is demonstrated by two assertions in that test: the planted true
relationship survives verification, and the planted false correlation does not.

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
| 6 | Falsification generator | `falsification/templates.py`, `generator.py`, `prompts.py` | **done** — deterministic template path (default) and DeepSeek V4 LLM path behind one interface; `get_generator` selects from config |
| 7 | Gateway orchestrator | `verification/gateway.py` | **done** — batch in, one proof object each out, BH applied once per run |
| 8 | Memory guard | `verification/memory_guard.py` | **done** — `assert_writable` / `writable`; the single choke point for `memory_write ⟹ verdict == PASS` |
| 9 | Tracing + structured logging | across the module | **done** — JSON logs carrying `insight_id` in executor, gateway and memory guard; Langfuse tracing on the LLM generation call (the module's only LLM call). See the note under *Known gaps*. |

## Suite status (2026-09-17)

```
pytest -q          # no ignores, no skips
322 passed
```

| Area | Tests |
|---|---|
| `tests/unit/contracts` | 52 |
| `tests/unit/verification` | 252 |
| `tests/integration` | 18 |
| **Total** | **322** |

Within `tests/unit/verification`: admissibility 28, bootstrap 10, config 19, effect
size 27, evidence 27, executor 48, falsification 39, fdr 23, gateway 7, memory guard
11, permutation 13.

Nothing is ignored and nothing is skipped. Every test file in the repository collects.

`ruff check .` passes across the repository.

## Acceptance test (`SCOPE.md` §6)

`tests/integration/test_gateway_e2e.py`, 18 tests, all passing. It runs the real
subprocess executor against the real templates; `n_permutations` is lowered to 1000 so
the suite stays usable, which moves the p-value floor and changes nothing else.

What it proves, on a 240-row toy frame built from a fixed seed:

| Planted | Claim | Result |
|---|---|---|
| Strong true correlation (`age` ~ `bmi`) | "bmi is associated with age" | **PASS / SUPPORTED**, effect 0.4165, q 0.00200, evidence score 0.867 |
| **False correlation** (`decoy` = shuffled `bmi`) | "decoy is associated with age" | **REJECT / INCONCLUSIVE**, effect -0.0042, q 0.95005 |
| Group difference (`area` ~ `income`) | "income tends to be higher in urban areas" | **PASS**, Cliff's delta 0.5739 |
| Monotonic trend (`month` ~ `visits`) | "visits is associated with month" | **PASS**, tau-b 0.3670 |
| Independent noise | three null claims | **REJECT** |
| Correct effect, wrong asserted direction | "bmi tends to be lower when age is higher" | **REJECT / REFUTED** |
| Five inadmissible claims | universal, causal, distribution, missing column, wrong arity | **REJECT / NOT_TESTABLE**, each with a reason, no statistics, no code |

Plus the structural guarantees: 13 candidates in, 13 complete proof objects out in
input order; the BH family is the 8 tested claims only, so the 5 screened-out ones do
not inflate the correction; one family id for the whole run; identical p-values and
q-values across repeated runs; and `writable()` returns only the SUPPORTED proofs.

`decoy` is the assertion that matters most. It is a shuffled copy of `bmi`, so it has
bmi's exact marginal distribution and zero association with anything. It is what a real
false positive looks like: it survives a glance at the summary statistics and dies
under a permutation test. A gate that passes it is broken whatever else it gets right.

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

- **Effect-size bands are still PROVISIONAL and are now OVERDUE for calibration**
  (`docs/OPEN_ISSUES.md` §11). The note there said they must be calibrated against the
  real NHANES / NFHS-5 subset *before the gateway is wired end to end*. The gateway is
  now wired end to end, so that deadline has passed. They pass the toy frame, which is
  built to sit above them by construction and therefore cannot validate them. **This is
  the highest-priority open item before the demo.**
- **Cramér's V is banded, gated and tested but structurally unreachable**
  (`docs/OPEN_ISSUES.md` §10). No `ClaimType` produces a contingency table. Still needs
  a decision: add a categorical claim type, or declare it out of scope.
- **`bootstrap_ci` is not wired to any template**, so `TestType.BOOTSTRAP` is
  unreachable and no proof object carries a confidence interval. Deliberate.
- **`mypy` does not pass cleanly**, for two separate reasons. With `pyproject.toml`'s
  pinned `python_version = "3.11"` it aborts inside the venv's numpy stubs, which use
  PEP 695 `type` statements requiring 3.12+ (the venv runs Python 3.13.6). Told the
  venv's actual version as a one-off diagnostic, it checks all 75 source files and
  reports 3 errors, all pre-existing in `executor/runner.py`: two are `resource.setrlimit`
  / `RLIMIT_AS` being absent from Windows stubs (the code already guards this with
  `try: import resource / except ImportError`, and the module docstring says so), and
  one is a `str | None` assigned to a `str`-inferred local that is guarded by an `or`
  at its use site. None is a correctness defect. Changing the pin is a shared-file,
  cross-module decision (`AGENTS.md` §8.7) and has not been made.
- **Langfuse tracing is local to this module.** `pramana.common.langfuse_client` and
  `pramana.common.logging` are B. Karthikeya's files and are still stubs on `main`, so
  the generator builds its own client and the JSON log records are formatted here. Both
  should delegate to the shared helpers once the orchestration spine merges.
- **`outlier_warning` is never set.** The templates report `outlier_divergence`, but
  `configs/verification.yaml` has no band for it and inventing a cutoff in code would
  violate `AGENTS.md` §3.3. Needs a configured threshold before the field means
  anything.
- **`RLIMIT_AS` under Docker on Linux — needs verification inside the Docker image.**
  The runner caps address space at `max_memory_mb` on POSIX. OpenBLAS reserves large
  virtual ranges at import, and a 1 GB address-space cap is known to break
  `import numpy` in some builds. This cannot be exercised on the Windows dev machine
  (the cap is advisory there; the container is the real enforcement). Run one
  template through the executor inside the image before relying on the cap.
- **`MIN_OBSERVATIONS` is both hardcoded (3, in `stats/`) and configured (20, in
  `verification.yaml`).** The stats floor is a "can this be computed at all" guard;
  the configured one is the gate's "is this worth concluding from" floor. Every
  template caller uses the configured value; the two are not in conflict, but the
  duplication is worth removing.

## Not started, and deliberately out of this scope

The evaluation / ablation harness (conditions A–D over the 40-dataset benchmark) is a
separate later work item per `SCOPE.md` §3. Only `src/pramana/evaluation/SPEC.md`
exists, as a proposal. Issues 2 and 3 in `docs/OPEN_ISSUES.md` stay open until the team
agrees the planted-truth design is what gets reported.

## Running it

```
cd pramana
.venv\Scripts\activate
pytest -q                  # 322 passed
ruff check .
pytest tests/integration/test_gateway_e2e.py -v    # the acceptance test alone
```
