# SCOPE.md: current scope

> One scope for the whole team. Context: `PROJECT.md`. Rules: `AGENTS.md`. State:
> `STATUS.md`. Next work, in order: `docs/ROADMAP.md`.
> First thesis review: Tue 27 Oct 2026. Code freeze: end of Mon 26 Oct (fix only what a
> rehearsal breaks). Rewritten 25 Oct 2026.
>
> Section numbers follow the gateway-era SCOPE.md, because about 45 code and test
> citations use them (`SCOPE.md 2 component N`, `SCOPE.md 4 step N`, `SCOPE.md 6`,
> `SCOPE.md 7`). Keep §2-§7 where they are; add new sections at the end.

## 1. Goal

Get the built product (PR #31 on `main`) reviewable and demonstrable: a stranger starts
the app with one command, drops a table, reads the Report, opens Checked claims and their
proofs, asks a question, and sees that only PASS claims reach memory. Then work through
`docs/ROADMAP.md` NEXT in order.

Acceptance journey: open http://127.0.0.1:8080, sign in, upload a table, read the
Report (Exact, then Measured), press Analyse, read held-up and rejected claims with
reasons, open a proof (q, effect, interval, scheme, split, attacks, seed, code), ask one
descriptive question in Ask, check the Memory page, download JSON/CSV.

## 2. In scope

The verification gateway components. Numbering is fixed; code docstrings cite it.

| # | Component | Where | State |
|---|---|---|---|
| 0 | Admissibility screen | `verification/admissibility.py` | built |
| 1 | Falsification code generator: template (default) and DeepSeek (`llm`, opt-in) | `verification/falsification/` | built |
| 2 | Sandboxed executor, import policy and HMAC provenance stamp | `verification/executor/`, `stats/provenance.py` | built |
| 3 | Statistics library: permutation, bootstrap, effect sizes, change, dependence | `verification/stats/` | built |
| 4 | BH-FDR correction, once per run | `verification/fdr.py` | built |
| 5 | Evidence scoring (ranks only, never gates) | `verification/evidence.py` | built |
| 6 | Verdict and proof object | `verification/gateway.py`, `contracts/` | built |
| 7 | Memory guard: the single PASS-only write path | `verification/memory_guard.py` | built |
| 8 | Gateway config: one file for every threshold and seed | `configs/verification.yaml`, `verification/config.py` | built |

Also in scope (all built; keep working and reviewable):

- Gateway v3 additions: permutation schemes and split, attacks A1-A7 and FRAGILE, effect
  interval, power note, spec hash, look ledger, refuter (off by default).
- Exact and Measured tiers, story and questions, planner and claim filters.
- Web UI (Report, Checked claims, Ask, Memory), accounts, export, chat, Skeptic, Explainer.
- Docs that match the code, tests, lint, and the items in `docs/ROADMAP.md`.

## 3. Out of scope (do not build, do not present as features)

- The A/B/C/D ablation and 40-dataset benchmark runs: a separate, parked work item
  (`PROJECT.md` §6). The library in `src/pramana/evaluation/` stays as it is.
- Categorical-versus-categorical claims (Cramér's V stays implemented but unreachable).
- Online FDR for chat (S9, parked) and Westfall-Young max-T (S10, not started).
- Letting a model write scikit-learn code in the sandbox (needs an AGENTS.md §4 change).
- Local-model (Gemma/Ollama) inference; any non-DeepSeek generative provider.
- More than one run at a time; a hardened internet-facing deployment.

Docker is tooling, not a person's module. Nobody "owns Docker". The executor only states
the sandbox constraints a container must satisfy (`AGENTS.md` §4).

## 4. Build order (gateway, all done)

The original nine gateway steps, kept because code cites them by number. All are built
and tested; later work extended them without changing their order.

1. Pydantic contracts (`CandidateInsight`, `ProofObject`).
2. Statistics library with known-answer tests (planted null gives a high p; planted
   effect gives a low p).
3. BH-FDR module, checked against statsmodels.
4. Evidence scorer: a deterministic function of q and effect; thresholds from config.
5. Sandboxed executor: timeout, import whitelist, memory cap, fail closed on crash.
6. Falsification code generator per claim type; generated code calls the vetted library.
   Unknown claim types fail closed, never "fall back to something generic".
7. Gateway orchestrator: generate, execute, collect p-values, BH, gate, proof objects.
8. Memory guard: thin, heavily tested; the only write path into memory. (Some docstrings
   also cite "step 8" for "a claim type with no template fails closed"; that rule lives in
   `admissibility.py` and `falsification/templates.py`.)
9. Langfuse tracing and structured logging across the gateway.

## 5. Definition of done (any change)

- Type hints, Pydantic-validated payloads, docstrings that state guarantees.
- Pytest coverage; statistical code gets known-answer tests.
- Thresholds and seeds in `configs/`, never inline.
- Structured logs carry `insight_id` inside the gateway.
- Fail-closed behaviour tested: a crashed or timed-out test can never yield PASS.
- Targeted tests and the full suite run before commit; `ruff check` clean for the
  files touched; PR description per `AGENTS.md` §8.9.

## 6. Acceptance test (end-to-end, mirrors the demo)

`tests/integration/test_gateway_e2e.py` feeds the gateway a small frame with planted
true relationships, a planted false correlation (a shuffled column), a wrong-direction
claim and inadmissible claims. Expected: true relationships PASS with sensible effects;
the decoy REJECTs; the wrong direction is REFUTED; inadmissible claims are NOT_TESTABLE;
every verdict carries a complete proof object; nothing REJECTed passes the memory guard.

## 7. Open items (carried deliberately)

Rows 1-7 keep their numbers from the gateway-era file; other docs cite them.

| # | Item | State on 25 Oct 2026 |
|---|---|---|
| 1 | Effect bands partly calibrated: only `spearman_rho` anchored on real data; the rest are convention, checked by simulation | unchanged; `docs/CALIBRATION_BANDS.md` |
| 2 | Categorical-versus-categorical claims out of scope | unchanged |
| 3 | `bootstrap_ci` not wired to a template | superseded: S5 adds a percentile-bootstrap effect interval to passing claims (shown, not gating; none for block-differenced trends). `TestType.BOOTSTRAP` is still unused as a test |
| 4 | Sen-slope O(n²) row ceiling (3,000 rows) | still there. Trend claims are dropped on tables above 3,000 rows, even when the test runs on period means; chat refuses trends there. Method change is an owner decision (ROADMAP) |
| 5 | Permutation cost | a live NHANES run took 259-375 s; per-stage cost not isolated |
| 6 | Generator default | `template` again since 24 Oct (AGENTS.md §2); `llm` is opt-in. `.env.example` and `docker/docker-compose.yml` still select `llm` |
| 7 | DeepSeek-vs-template agreement measured on one 9-claim live run only | unchanged; `llm` is opt-in, so its refusal rate at scale is unmeasured |
| 8 | Gateway v3 sign-off sheet rows 1-9 are unticked although the code is merged | owner to sign or disclose (`docs/GATEWAY_V3_STATUS_AND_SIGNOFF.md` §5) |
| 9 | BH on correlated claim families and real-data attack false-kill rate unmeasured | ROADMAP NEXT |

## 8. Limitations to state at review

- PASS supports an association on the held-back rows of this table, not causation. One
  attack (A3, third-variable control) can demote a PASS to FRAGILE; there is no
  regression adjustment. The Skeptic adds descriptive confound caveats; it never changes
  a verdict.
- The split protects against the model choosing claims on the rows it is tested on, not
  against reuse: the look ledger discloses reuse, it does not block it. Chat claims have
  no split and are single tests (q = p).
- Effect floors remove trivial large-n effects; they do not separate truth from chance.
- The report card uses families of one, so BH under dependence is not measured.
- Validation is mostly synthetic (planted facts, planted nulls).
- The planner proposes different claims on different runs; each claim is reproducible
  from its stored code and seed, the family is not.
- Measured needs several numeric columns and has no null distribution for its lift; it
  never reaches the gate or memory.
- One run at a time; memory is shared across accounts.

## 9. Citation key

Older citation styles that still appear in the repo:

- `SCOPE.md 2 component N`, `SCOPE.md 4 step N`, `SCOPE.md 6`, `SCOPE.md 7`: this file,
  sections above (same meaning as the gateway-era file).
- `SCOPE.md section 6` meaning "limitations" (V1-era file of 22 Oct): now §8.
- `scope/SCOPE_*.md`: per-person files removed on 22 Oct (PR #27). Read them with
  `git show fa5bcea^:scope/SCOPE_P_Rohith.md` (and `_B_Karthikeya`, `_M_Karthik_Reddy`).
- The gateway-era file itself: `git show fa5bcea^:SCOPE.md`.
