# Open Issues — Verification Gateway

> **STALE STATUS WARNING (16 September 2026).** The build-status claims in this file —
> the "Where the code actually stands" table and the "Built since (3 September 2026)"
> section — are **out of date and overstate what exists**. `docs/IMPLEMENTATION_STATUS.md`
> is the current source of truth for what is implemented. The *decisions* recorded here
> (issues 1-9) remain valid; only the status claims are wrong. Corrections are marked
> inline below.
>
> Written by: P.P. Satya Karthikeya (verification module)
> Status: issues 1, 4, 5 and 6 are DECIDED and now IMPLEMENTED (see the bottom section).
> 2 and 3 have a proposed answer in `src/pramana/evaluation/SPEC.md` and need the team.
> New since: 7 (a contract change to announce), 8, 9.
> Plain-English version. Details live in `PROJECT.md`, `AGENTS.md`, `SCOPE.md`.

## Decisions taken (2 September 2026)

| # | Decision | Written into |
|---|---|---|
| 1 | One run = one gateway invocation = one BH family. A claim is tested **once**. REFUTED/INCONCLUSIVE claims are never revised and resubmitted to the same gate — revisions go to the next run. Graph-level retries cover crashed code only, and the counter stays with the graph (B. Karthikeya). | `PROJECT.md` §2 |
| 4 | Reworded. The guarantee comes from the sandbox and the import whitelist, not from model choice. The verification model is swappable; a deterministic template renderer is the default generator and the baseline the LLM is measured against. | `PROJECT.md` §3, `SCOPE.md` §2 |
| 5 | `NOT_TESTABLE` added as a fifth `GateOutcome`, mapping to `verdict = REJECT`. It is produced by a new admissibility screen that runs **before** code generation. Untested claims have no p-value and are **excluded from the BH family** and from `n_hypotheses_in_batch`. | `PROJECT.md` §2, `SCOPE.md` §2 component 0 |

**New (6): unfalsifiable claim wording.** A permutation test can support "X tends to be
higher when Y is higher". It can never support "X **always** increases Y", and no p-value
licenses a causal verb on observational survey data. Universal quantifiers (always, all,
never, every, none, guarantees) and causal verbs are refused as `NOT_TESTABLE` at the
gateway entrance. Upstream fix, cheaper and cleaner: Rohith's module emits claims from
fixed hedged sentence templates, so the wording never arises. The gateway screen is the
safety net, not the main defence.

---

Six things I think are wrong, missing, or undecided in PRAMANA. Each one is written
as: **what the problem is**, **why it matters**, **what we need to decide**.

**Three are now resolved (1, 4, 5) and are marked RESOLVED inline — the decision
replaces the "what we need to decide" block. Two are still open and need the team:
2 (benchmark ground truth) and 3 (a fair Condition C). Issue 6 is new.**

---

## 1. The retry loop can break our main statistical promise — **RESOLVED**

**What we promise.** We test many insights in one run. Some will look real just
by luck. Benjamini-Hochberg (BH) is the maths that keeps those lucky flukes
under control. It works by looking at *all* the tests in a run together.

**The problem.** When the gateway says REFUTED or INCONCLUSIVE, the agent is
told why, it changes the insight, and sends it back. That is good for the
product. But it is bad for the maths.

Think of it like this: you take an exam, you are told which answers were wrong,
you change those answers, and you take the same exam again. Your final score
looks better than your real knowledge. That is exactly what the retry loop does
to our data. The agent gets to peek at the answer and try again.

BH only corrects the tests inside **one** batch. It does not know that some of
those insights are second or third attempts, already guided by earlier results.
So the real false-discovery rate is higher than the number we print.

**Also:** nobody has written the retry loop down. `PROJECT.md` §2 does not
mention it. `SCOPE_B_Karthikeya.md` mentions retry only for *code that crashed*,
which is a completely different thing. So this sits in a gap between my module
and B. Karthikeya's, and neither of us owns it yet.

**DECIDED.** No re-testing within a run. One run = one gateway invocation = one BH
family, and every candidate is tested exactly once. A REFUTED or INCONCLUSIVE claim is
not revised and resubmitted to the same gate; revisions belong to the next run on the
next dataset. The retry counter stays with the graph and covers **crashed code only**.

**This changes the product loop, and B. Karthikeya must be told directly.** The old
picture — gateway returns a reason, agent revises, resubmits, gives up after N tries —
no longer exists inside a run. His LangGraph must have **no edge from the gateway back
to the analysis agent** except for crashed execution. If he builds that edge from the
old diagram, the FDR guarantee breaks silently and no test will catch it.

Written into `PROJECT.md` §2.

---

## 2. We have no way to score the benchmark

**What we promise.** We run four versions of the system (A, B, C, D) on 40
datasets and show that D — full PRAMANA — reports more correct insights than
the others.

**The problem.** To say "this insight was correct", somebody has to already know
the correct answer for that dataset. We have not written down where that answer
comes from. No document says it. `src/pramana/evaluation/` is empty.

Without this, the whole comparison cannot be scored. We would have four sets of
outputs and no way to say which set is better.

**What we need to decide.** Where does ground truth come from? Options:
- Use published papers on NHANES / NFHS-5 and take their findings as the truth.
- Plant known relationships into datasets ourselves, so we know the answer by construction.
- Have humans label a sample of the outputs.

This is my module and it is the part that proves the whole project. It should
not stay empty.

---

## 3. Condition C is our real competitor, and a weak version proves nothing

**What we promise.** D beats C. C is "agent + an LLM that judges insights,
with no code execution".

**The problem.** C is the closest thing to what everyone else builds. If we
build a lazy version of C, we win against a strawman and the result means
nothing. Any reviewer will ask whether C was built seriously.

**What we need to decide.** Give C a proper prompt and a fair budget. Treat it
as if we were trying to make it win.

---

## 4. The DeepSeek reason in PROJECT.md is stated wrongly — **RESOLVED**

**What the doc says.** `PROJECT.md` §3 says we must use DeepSeek V4 for
verification, and that using a weak local model would "undermine the trust
thesis".

**The problem.** That reason is not right, and it makes us look confused about
our own design.

DeepSeek does not decide anything. It only **writes** the test code. Then:
- the code runs in a locked sandbox,
- `scipy`, `statsmodels` and `sklearn` are blocked inside it,
- so the code has no choice but to call our own vetted functions,
- and **our** Python computes the p-value, the q-value, the effect size and the verdict.

So the trust does not come from the model being smart. It comes from the
architecture: the model is not allowed to touch the maths.

**Why this matters.** The corrected version is a *stronger* argument, not a
weaker one. It says our guarantee holds even if the LLM is bad. It also means
we could use a cheaper model here if cost becomes a problem.

**DECIDED.** `PROJECT.md` §3 reworded: the guarantee comes from the sandbox and the
import whitelist, not from the model choice. The model is swappable, and a
deterministic template renderer is the default generator with the LLM behind the same
interface.

**And the config now matches the prose, which it did not before.** `scipy` and
`sklearn` were still on `executor.allowed_imports` — generated code could have called
`scipy.stats.pearsonr` and the whole argument would have collapsed. They are removed,
and `ExecutorConfig` now *raises* if any statistics library appears in the whitelist,
so the guarantee cannot be voided by a future config edit. `configs/verification.yaml`
also gained `llm.generator: template` to name the default.

**Still outstanding, and it is a TEAM decision:** `AGENTS.md` §4 still reads
"Whitelist imports (numpy, pandas, scipy, sklearn stats only)". That is a shared file,
so it is not mine to change alone — but as it stands the project's rulebook contradicts
the project's central claim. Raise it with the team.

---

## 5. Small: one verdict has no home in the code — **RESOLVED (decided, not yet built)**

We describe five outcomes: SUPPORTED, REFUTED, NEGLIGIBLE, INCONCLUSIVE and
NOT_TESTABLE. The `GateOutcome` enum in `src/pramana/contracts/enums.py` has
only the first four. NOT_TESTABLE — "this claim is outside what the gateway can
check" — has nowhere to go yet.

Small fix, but it should happen before the gateway orchestrator is written, or
the orchestrator will invent its own way of saying it.

**DECIDED — and it forces a contract change, so the shape is fixed here first.**

`NOT_TESTABLE` is a fifth `GateOutcome` mapping to `verdict = REJECT`. It is produced
by the admissibility screen *before* any code is generated. But a screened-out claim
was never tested, and `ProofObject` today requires a full statistical record from
every proof object:

| Field | Today | A NOT_TESTABLE claim has |
|---|---|---|
| `p_value` | required float | nothing — never tested |
| `q_value` | required float | nothing — excluded from the BH family |
| `n_hypotheses_in_batch` | `ge=1` | it is not in the family at all |
| `test_type` | required | no test ran |
| `falsification_code` | required | no code was generated |
| `effect_size`, `effect_metric` | required | nothing computed |

So the contract must change alongside the enum: those fields become nullable **for
`NOT_TESTABLE` only**, enforced by a validator — null iff `NOT_TESTABLE`, and
`failure_reason` mandatory in that case. Every other outcome keeps the full record.

There are now **two** kinds of proof object that carry no successful test, and the
docstring must say both: a crashed or timed-out test (code ran, failed, fail-closed →
still has `falsification_code` and a `failure_reason`) and a screened-out claim (no
code, no test, no statistics at all). Do not collapse them — one is an execution
failure, the other is a claim we refused to test on principle.

---

## Things that must be SAID to someone, not just written here

A decision recorded in a file nobody re-reads is not a decision. Three of these change
what a teammate builds:

| Tell | Who | What changes for them |
|---|---|---|
| No in-run re-testing (issue 1) | B. Karthikeya | His graph must have **no gateway → analysis edge** except for crashed code. Building it from the old diagram breaks the FDR guarantee silently, and no test catches it. |
| Hedged claim sentences (issue 6) | P. Rohith | Candidate claims come from fixed templates using "is associated with" / "tends to be higher in" — never always, all, never, causes. Otherwise my screen becomes the main defence instead of a safety net, and it will reject a lot of his output. |
| Whitelist contradiction (issue 4) | Whole team | `AGENTS.md` §4 still permits scipy and sklearn in the sandbox. Shared file, team decision, but it currently contradicts our central claim. |

---

## Where the code actually stands (2 September 2026)

| Part | Owner | State |
|---|---|---|
| Contracts, stats, BH-FDR | Satya Karthikeya | done, 171 tests passing (16 Sept) |
| Evidence scorer | Satya Karthikeya | **stub** — the "done" claim in the 2 Sept version of this row was wrong |
| Sandbox executor, falsification generator, gateway, memory guard | Satya Karthikeya | stubs |
| Evaluation / ablation harness | Satya Karthikeya | empty |
| Analysis module | Rohith | stubs |
| Orchestration graph | B. Karthikeya | stubs |
| Memory, API, dashboard | Karthik Reddy | stubs |

The deterministic core of the gateway is finished and tested. Nothing else in
the repo runs yet, and no part of the system runs end to end.

---

## Built since (3 September 2026)

Decisions 1, 4, 5 and 6 are now implemented, not just written down.

> **CORRECTION (16 September 2026).** The original version of this paragraph claimed
> "the whole gateway runs end to end, offline, with no API key and no teammate module."
> **That was not true and is not true today.** The gateway orchestrator, the sandboxed
> executor, the generator entry point and the memory guard are still stubs, so nothing
> runs end to end yet. What exists is the deterministic core listed below plus the
> contracts, config loader, statistics library and BH-FDR correction. The
> `tests/integration/test_gateway_e2e.py` row below is the acceptance test's SOURCE,
> which is written; it does not pass yet.

| Piece | Where |
|---|---|
| `NOT_TESTABLE` + null-iff-untested contract | `contracts/enums.py`, `contracts/proof_object.py` |
| Admissibility screen | `verification/admissibility.py` |
| Memory guard | `verification/memory_guard.py` |
| Template falsification generator | `verification/falsification/templates.py`, `generator.py` |
| Sandboxed executor + provenance stamp | `verification/executor/`, `verification/stats/provenance.py` |
| Gateway orchestrator | `verification/gateway.py` |
| Acceptance test | `tests/integration/test_gateway_e2e.py` |
| Evaluation spec (D) | `src/pramana/evaluation/SPEC.md` |

### 7. Contract change to announce: `reference_group`

`CandidateInsight` gained one additive optional field, `reference_group`. It is needed
because a direction is meaningless for a two-group claim without one: Cliff's delta is
signed relative to whichever group the code puts first, which is a convention, not
something the claim states. Without it the gate would emit REFUTED for what is really a
label-ordering artifact, so the direction check is SKIPPED for two-group claims that do
not name a reference group.

Additive and optional, so nothing upstream breaks. But `contracts/**` is consumed by all
four modules and `OWNERSHIP.md` says schema changes are announced before they are merged,
not after. **This is the announcement — it needs a nod from the team.**

### 8. What the provenance stamp does and does not do

The sandbox whitelist blocks statistics LIBRARIES, not arithmetic: generated code with
only numpy and pandas can still hand-roll a permutation loop, or call
`frame.corr(method="spearman")`, which needs no scipy at all. So `permutation_test` now
HMACs its own result with a per-run nonce and the parent rejects anything unstamped.

Stated honestly, because the report will be read by someone who asks: this is an
ADHERENCE check, not a security boundary. It catches generated code that bypassed the
vetted function. It would not stop hostile code, because anything running inside the
subprocess can reach the nonce. We do not need it to -- the code is written by our own
generator against our own prompt. Claiming more than that in the report would be exactly
the kind of overreach this project exists to argue against.

### 9. Still open, and still needs the team

- **`AGENTS.md` section 4** still reads "Whitelist imports (numpy, pandas, scipy, sklearn
  stats only)". It now contradicts `PROJECT.md` section 3, `configs/verification.yaml`,
  and a config loader that will REFUSE to start if anyone follows it. Shared file, so it
  needs sign-off rather than a unilateral edit.
- **B. Karthikeya:** the LangGraph must have **no edge from the gateway back to the
  analysis agent**, except for crashed code. Building it from the old diagram breaks the
  FDR guarantee silently, and no test in this repo can catch it -- the graph is not ours.
- **P. Rohith:** candidate claims must come from fixed hedged sentence templates ("is
  associated with", "tends to be higher in") -- never always / all / never / causes. The
  screen in `admissibility.py` is the safety net, not the main defence, and every claim
  it refuses is a wasted candidate slot. The analysis module must also emit effect
  MAGNITUDE only, never p-values: exploratory statistics rank candidates, they never
  judge them.
- **Issues 2 and 3** (benchmark ground truth, a fair Condition C) are answered in
  `src/pramana/evaluation/SPEC.md` as a proposal. They stay open until the team agrees
  the planted-truth design is what we are reporting.

### 10. Cramer's V is banded and gated but structurally unreachable

`EffectMetric.CRAMERS_V` exists, `configs/verification.yaml` gives it a band, and
`test_evidence.py` specifies its table-size threshold scaling in detail. But no
`ClaimType` produces it: `templates.py` emits only `spearman_rho`, `kendall_tau_b`,
`cliffs_delta` and `epsilon_squared`, and there is no categorical-vs-categorical claim
type for a contingency table to come from. So the metric can never fire.

This matters because NHANES / NFHS-5 demographic data is exactly where two-categorical
associations live (area x education, region x insurance status). **Decide one way or
the other and write it down:** either add a `categorical_association` claim type (a
contract change, so it needs the same announcement as issue 7), or declare it out of
scope in `SCOPE.md`. Leaving it as-is means a reviewer finds tested, configured,
unreachable code and asks why.

### 11. Effect-size bands are provisional, not calibrated

The five per-metric bands in `configs/verification.yaml` were chosen to be defensible
and to satisfy structural constraints in the test suite (for example `tau.min <
rho.min`), **not** by calibrating against the demo data. They are marked `PROVISIONAL`
in the config file. They decide what PASSes, so they must be calibrated against the
real NHANES / NFHS-5 demo subset **before the gateway is wired end to end**
(`SCOPE.md` 4 step 7) -- discovering during the live demo that a floor rejects the
planted true relationship is the failure mode this note exists to prevent.
