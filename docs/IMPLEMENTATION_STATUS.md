# IMPLEMENTATION_STATUS.md — verification gateway, current state

> **Historical snapshot.** Current project status is in [STATUS.md](../STATUS.md). Figures and branch names below are from the date of writing and may be out of date.

> Scope: `src/pramana/verification/`, `src/pramana/contracts/`, `tests/`, and
> `configs/verification.yaml` (Satya Karthikeya's module). Other members' folders are
> not tracked here. Last updated 2026-10-14, after the finishing pass (WP1-WP7, below).

## Headline

**All nine phases of `SCOPE.md` §4 are implemented and the full suite is green: 322
passed, zero failures, zero collection errors.** The gateway runs end to end. The
`SCOPE.md` §6 acceptance test passes against real code at every layer — real
admissibility screen, real template generator, real subprocess executor, real BH-FDR,
real evidence gate, real memory guard, and no mocks anywhere in the statistical path.

The product claim is demonstrated by two assertions in that test: the planted true
relationship survives verification, and the planted false correlation does not.

## Finishing pass (2026-10-14, branch `feat/gateway-finish`)

Built after Phase 9. Each item is committed separately; the full suite is **632
passed, 0 failed** with `DEEPSEEK_API_KEY` unset (about 12 minutes), and `ruff check .`
passes. The suite still has no ignores and no skips.

| Item | What changed | State |
|---|---|---|
| WP1 | The LLM prompt's return contract is now derived from the executor's `REQUIRED_KEYS`; a required key with no prompt wording raises at build time. Before this, every LLM-written program was refused (`reported_effect` was missing from the prompt). | done |
| Gateway fix | A program returning `reported_effect` without `reported_effect_metric` used to reach PASS. It is now INCONCLUSIVE / REJECT and stays in the BH family at p = 1.0. | done |
| WP2 (W1) | `check_columns` in `executor/policy.py`: static refusal of generated code that reads columns outside the claim's `variables` or filters rows the claim does not state. Runs before any subprocess. It is a static AST check, not a proof; its limits are written at the top of the section. | done |
| WP3 (W2, W3) | Verification tests are pinned to `generator: template` (`tests/fixtures/config.py`). `llm.generator` in `configs/verification.yaml` is now `llm` (D1); `template` stays as the reference and offline mode. `PRAMANA_VERIFICATION_GENERATOR` overrides that one value (`template` or `llm`, anything else raises). | done |
| Logging | LLM-path column-check refusals are counted per claim type (`column_check_refused` events, `column_check_summary` per batch). `check_columns` was not loosened. | done; first live measurement 2026-10-18 (below) |
| Generator unavailable | `GeneratorUnavailable` separates "the generator could not be reached" from "the claim is untestable". `verify_batch_with_summary` returns `(proofs, BatchSummary)` with `generator_unavailable_count`; one WARNING per batch. Per-claim verdicts are unchanged. `verify_batch` still returns the proofs only. | done |
| WP4 (W8) | On the LLM path each tested claim's template program is also run; a separate shadow BH family and the same gate give the template outcome. Differences are flagged in `BatchSummary.template_disagreements` and as WARNING events. Diagnostic only: it cannot change a verdict, p, q or the real family. Costs roughly 2x sandbox time per LLM-path run. | done |
| WP5 | Effect-size bands: `spearman_rho` measured on the demo frame; `kendall_tau_b`, `cliffs_delta` and `epsilon_squared` checked by known-answer simulation (2026-10-20, `scripts/calibration/simulate_bands.py`); no band value changed. `cramers_v` out of scope. Open: the stricter-tier policy choice. See `docs/CALIBRATION_BANDS.md`. | done except policy choice |
| WP6 | `src/pramana/evaluation/`: planted-dataset builder, conditions A and D as flags on one pipeline (B and C raise `NotImplementedError`), precision / recall / empirical FDR, per-condition table, SPEC section 5 run log, `configs/evaluation.yaml`. | done for A and D |
| WP7 | The three hardcoded `3`s in `stats/` are one named constant, `MINIMUM_COMPUTABLE_OBSERVATIONS`; behaviour pinned by tests written first. `outlier_warning` and Cramer's V are proposals only. | partly; two decisions open |

**First live DeepSeek run (2026-10-18).** 9 claims on `data/demo_nhanes_small.csv` (5 correlation,
2 group difference, 2 trend), one gateway invocation, `generator: llm`. It found two prompt defects,
both fail-closed (no false PASS) but together a 100% refusal rate for group_difference:
(1) the prompt never said `permutation_test_groups` calls `statistic` with one list argument, so
the model passed `cliffs_delta` bare (`missing 1 required positional argument: 'b'`); (2) the
model built groups with row filters `check_columns` refuses. Both were fixed in
`falsification/prompts.py` by showing the accepted form, with tests written first
(`tests/unit/verification/test_prompts.py`); `check_columns` was not loosened. After the fix:
9/9 programs accepted, 0 column-check refusals, 0 template disagreements, planted shuffled decoy
and 40-row pilot decoy both REJECT, BMI/glucose, age/glucose, age/BMI, sex-glucose and both
trends PASS. This is one small run on one frame: it shows the path works, not what the refusal
rate is at scale.

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

## Suite status (2026-09-17; superseded by the finishing-pass count above)

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

- **Effect-size bands: PARTLY CALIBRATED (2026-10-14).** Only `spearman_rho` is
  measured, against the demo frame; the other four metrics have no planted anchor.
  `docs/CALIBRATION_BANDS.md` has the table and the open stricter-floor decision. The
  paragraph below is the original note, kept for history.
- **(original note) Effect-size bands are still PROVISIONAL and are now OVERDUE for calibration**
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
- **`outlier_warning` is never set.** A proposal (config key
  `evidence.outlier_divergence_warn`, value 0.30, reporting only) is written in
  `docs/WP7_PROPOSALS.md` and awaits approval. No code was changed.
- **`RLIMIT_AS` under Docker on Linux — needs verification inside the Docker image.**
  The runner caps address space at `max_memory_mb` on POSIX. OpenBLAS reserves large
  virtual ranges at import, and a 1 GB address-space cap is known to break
  `import numpy` in some builds. This cannot be exercised on the Windows dev machine
  (the cap is advisory there; the container is the real enforcement). Run one
  template through the executor inside the image before relying on the cap.
- **`MIN_OBSERVATIONS` duplication: RESOLVED (2026-10-14).** The hardcoded 3s are one
  constant, `MINIMUM_COMPUTABLE_OBSERVATIONS`, documented as not a conclusion threshold;
  the gate's configured 20 is unchanged. Behaviour is pinned by characterization tests.

## Not started, and deliberately out of this scope

The evaluation / ablation harness is a separate later work item per `SCOPE.md` §3.
Conditions A and D are now built (see WP6 above); B and C are `NotImplementedError`
stubs, and the 40 pre-shuffle benchmark extracts do not exist yet (P. Rohith).
`synthetic_extract` stands in for them and is not benchmark data. Issues 2 and 3 in `docs/OPEN_ISSUES.md` stay open until the team
agrees the planted-truth design is what gets reported.

## Running it

```
cd pramana
.venv\Scripts\activate
pytest -q                  # 632 passed (about 12 minutes)
ruff check .
pytest tests/integration/test_gateway_e2e.py -v    # the acceptance test alone
```
