# Handoff prompt — decisions to apply to PRAMANA

> Paste everything below the line into Claude Code, from the repo root.
> It states what was decided, what is already applied, and what is left to build.
> Owner of every change below: P.P. Satya Karthikeya (verification module) unless marked.

---

Read `PROJECT.md`, `AGENTS.md`, `SCOPE.md` and `docs/OPEN_ISSUES.md` first.

A design review produced the decisions below. Some are already written into the repo —
do **not** redo those, just don't contradict them. The rest are yours to implement, in
the order given. Follow `AGENTS.md`: stay inside `src/pramana/verification/`,
`src/pramana/contracts/`, `configs/verification.yaml` and `tests/`, and flag anything
that would weaken `memory_write ⟹ verdict == PASS` instead of implementing it.

## A. Already applied — treat as settled

1. **No re-testing inside a run.** One run = one gateway invocation = one BH family;
   every candidate is tested exactly once. A REFUTED or INCONCLUSIVE claim is never
   revised and resubmitted to the same gate — that is testing after peeking, and it
   inflates the true FDR. Graph-level retries cover **crashed code only**.
   (`PROJECT.md` §2)

2. **The trust guarantee comes from the sandbox, not the model.** The verification LLM
   generates only; it computes nothing. The model is swappable. A deterministic template
   renderer is the DEFAULT generator, with the LLM behind the same interface.
   (`PROJECT.md` §3) **Superseded 18 Sep 2026 for the default only:** decided that
   DeepSeek becomes the default and the template the reference; not yet switched
   (`docs/DECISIONS_LLM_ROLES.md` D1).

3. **Whitelist tightened.** `scipy` and `sklearn` removed from
   `executor.allowed_imports`; only `numpy`, `pandas`, `pramana.verification.stats`
   remain. `ExecutorConfig.model_post_init` now raises if any statistics library appears
   in the whitelist (`FORBIDDEN_SANDBOX_IMPORTS`).

4. **`llm.generator: template`** added to `configs/verification.yaml`, with a matching
   `generator: Literal["template", "llm"]` field on `LLMConfig`. The value switches to
   `llm` once W1 and W2 in `docs/DECISIONS_LLM_ROLES.md` land (and W13 for any deployed
   setup).

5. **Admissibility screen decided** (see B1) and recorded in `PROJECT.md` §2 and
   `SCOPE.md` §2 component 0.

## B. To implement, in this order

### B1. `NOT_TESTABLE` + admissibility screen

Add `NOT_TESTABLE` to `GateOutcome` in `src/pramana/contracts/enums.py`, mapping to
`Verdict.REJECT`.

`ProofObject` must change with it. A screened-out claim was never tested, so these
fields become **nullable, but only when `gate_outcome is NOT_TESTABLE`**, enforced by a
validator (null iff NOT_TESTABLE):

- `p_value`, `q_value` — no test ran, and the claim is not in the BH family
- `n_hypotheses_in_batch` — currently `ge=1`; it is not a family member at all
- `test_type`, `falsification_code`, `effect_size`, `effect_metric`

`failure_reason` becomes mandatory for `NOT_TESTABLE`.

The class docstring currently says a crashed test still produces a full proof object.
There are now **two** no-result cases and it must say both:
- crashed / timed out — code was generated and ran, so `falsification_code` exists
- screened out — no code, no test, no statistics at all

Then write the screen as `admissibility.py` in `src/pramana/verification/`. It runs
FIRST in the gateway, before any generation, and refuses:
- universal/absolute wording: always, never, all, every, none, guarantees. A permutation
  test can support "tends to be higher"; it can never support "always".
- causal verbs on observational data: causes, leads to, makes.
- `claim_type = distribution` — no template in this scope.
- variables absent from the cleaned dataframe.

Refused claims get `NOT_TESTABLE` and are **excluded from the BH family and from
`n_hypotheses_in_batch`**.

### B2. Tests for `FORBIDDEN_SANDBOX_IMPORTS`

The one check enforcing the project's central claim is currently untested. Three tests:
a config listing `scipy` raises; a clean config loads; `pramana.verification.stats` is
still allowed even though it imports scipy internally.

### B3. Test fixture — fake candidates

`tests/fixtures/`: hand-written `CandidateInsight` batches plus a toy dataframe with one
planted signal, one shuffled column, and some pure-noise columns. This unblocks
everything below without waiting on the analysis module.

### B4. Memory guard

`src/pramana/verification/memory_guard.py`: one function, raises unless
`verdict == PASS`, returns the proof otherwise. Ten lines plus tests. This is where
`AGENTS.md` §0 physically lives.

### B5. Template falsification generator

Deterministic f-string renderer per `claim_type` (`correlation`, `group_difference`,
`trend`). No LLM, no API key, no network. `distribution` → `NOT_TESTABLE`.
Generated code must call `pramana.verification.stats` and print one JSON line:
`{p_value, effect_size, effect_metric, reported_effect, seed}`.

### B6. Sandboxed executor + provenance stamp

Subprocess with timeout, AST-checked import whitelist, JSON-line output contract.
Crash, timeout, or unparseable output → fail-closed, never a p-value. Must work as a
plain synchronous call (Celery wrapping is B. Karthikeya's).

**Known hole this must close:** the whitelist blocks statistics *libraries*, not
*arithmetic*. Generated code can still hand-roll a permutation loop in numpy or call
`df.corr(method='spearman')`, and hand back a fabricated number. Fix with a provenance
stamp: pass a per-run nonce into the subprocess via env; `permutation_test` HMACs
`(statistic, p_value, n_permutations, seed, nonce)` onto its result; the parent
recomputes the digest and rejects anything that does not verify. A fabricated number
cannot be stamped without calling the real function.

### B7. Gateway orchestrator

`verify_batch(candidates, frame, config) -> list[ProofObject]`:
screen → generate → execute → collect p-values → **BH once** → gate → proof objects.
Plain synchronous Python. Structured logs carrying `insight_id` throughout.

### B8. End-to-end test

Toy frame with one planted true relationship, one planted false correlation, several
nulls. Assert: true → PASS with a sensible effect; false → REJECT; every claim has a
complete proof object; nothing REJECTed survives the memory guard.

## C. Design direction — do not build yet, but do not contradict

**The generator should eventually emit a test specification, not code.** The strongest
version of the guarantee is that the model never produces a number at all: it names the
test, the columns, the statistic, the alternative and the asserted direction, and our
code runs it. The template renderer in B5 is already this design with the model removed.
The provenance stamp in B6 is the interim fix for the code-generating design. Keep the
generator interface narrow enough that swapping to specs later is not a rewrite.

## D. Evaluation — changed design

**There is no LLM-critic component in the product.** Adding a second LLM muddies the
design, and filtering candidates on the observed statistics would reintroduce the
peeking problem that decision A1 exists to prevent.

Condition C is an **evaluation-only mode**, not a component: the same model, the same
claims, the same information — but the test is skipped and the model is asked to judge
instead. Fair by construction, because it is our own system with execution switched off.

Conditions become flags on one codebase:
- A — single LLM call, no loop
- B — agent loop, no gate
- C — same model asked to judge, nothing executed
- D — full pipeline

**Ground truth is planted, by construction.** Take real NHANES / NFHS-5 column
marginals, independently shuffle every column to destroy all real associations, then
inject k relationships with known effect size and direction from a logged seed. Every
other pair is a true null, so precision and recall are exact and reproducible. Published
paper-linked effects are used only on the one or two demo datasets. Write this as a spec
in `src/pramana/evaluation/` before building the harness.

## E. Asks that belong to other people — do not implement, raise them

- **`AGENTS.md` §4** still reads "Whitelist imports (numpy, pandas, scipy, sklearn stats
  only)", which now contradicts `PROJECT.md` §3 and the config. Shared file — needs team
  sign-off, not a unilateral edit.
- **B. Karthikeya:** the LangGraph must have **no edge from the gateway back to the
  analysis agent**, except for crashed code. Building it from the old diagram breaks the
  FDR guarantee silently and no test catches it.
- **P. Rohith:** candidate claims must come from fixed hedged sentence templates ("is
  associated with", "tends to be higher in") — never always / all / never / causes. And
  the analysis module emits **effect magnitude only, never p-values**; exploratory stats
  rank candidates, they never judge them.
