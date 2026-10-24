# Prompt: continue the verification gateway in a cloud session

Paste the block below into a Claude Code cloud session on the repository
`satyakarthikeya/pramana`. Start the session from branch
`docs/satya/gateway-v3-design` (it holds the design doc and this file).

---

You are continuing work on PRAMANA's verification gateway. Read these first, in order,
and do not start coding before you have:

1. `AGENTS.md` (rules; §0 prime directive and §3 statistics rules are non-negotiable)
2. `docs/DESIGN_verification_gateway_v3.md` (the plan: steps S1 to S10)
3. `src/pramana/verification/gateway.py`, `schemes.py`, `attacks/runner.py`,
   `configs/verification.yaml`, and `src/pramana/contracts/`
4. `docs/PLAN_analysis_platform.md` §13 (what was built and decided so far)

## Ground rules

- Models propose; code decides. No model computes a number, writes a verdict, or
  argues a claim is true. No raw rows go to any model.
- `memory_write => verdict == PASS` must hold. A gate REJECT can never be upgraded by
  an attack. Add a test that fails if either breaks.
- Thresholds live only in `configs/verification.yaml`. Seeds are configured and logged.
- Do ONE step of the design per branch and per pull request. Branch name
  `feat/satya/gateway-<short-step>`, from the branch you were started on (the work
  builds on unmerged PR 29; say so in each PR body, AGENTS.md §8.2).
- Conventional Commit subjects under 72 characters. End commit messages with the
  attribution line the harness gives you. Never commit secrets, `.env` files or data.
- You have no DeepSeek or Langfuse credentials in the cloud. Tests must use fakes and
  must never need a network. Never weaken fail-closed behaviour to make a test pass.

## Environment

- Python 3.11+. Create a venv and install the project and dev extras from
  `pyproject.toml`. Frontend is in `web/` (Vite, React, TypeScript); run
  `npx tsc --noEmit` there if you touch it.
- Run targeted tests for what you changed, e.g.
  `python -m pytest tests/unit/verification -q`. The full suite
  (`python -m pytest -p no:cacheprovider -rfE`) took about 32 minutes locally; run it in
  the background before opening a PR and report the result honestly, including any
  failure.

## Stop and ask the owner (do not decide these yourself)

The verification owner is P.P. Satya Karthikeya. Steps S4 to S10 in the design doc
touch contracts, the model's role in the gateway, the split, or FDR. Before coding one
of those, write a short "decision needed" note in the PR description (what, why, the
options) and stop. S1, S2 and S3 do not need a decision.

## Your task, in order

1. **S1 (wording and power note).**
   - FRAGILE reads "passed the significance test, but did not hold under <check>".
   - REJECT reads "not enough evidence at this sample size", with n and effect size.
   - Nothing says "proven", "correct" or "true". PASS reads "held up", with how many
     applicable checks it survived.
   - Add a power note on every REJECT: the smallest effect the confirmation rows could
     have detected at the run's alpha. Compute it in `pramana.verification` code (not in
     the UI), cap its cost through config, and add known-answer tests.
   - Touch API wording in `src/pramana/api/v1.py` and the web proof cards; keep the
     exhaustive TypeScript `never` switches exhaustive.
   - No change to any p-value, FDR, band or split logic in this step.
2. **S2 (gate report card).** Add `scripts/calibration/gate_report_card.py` and a CI
   test that print and assert: false-positive rate on planted nulls per scheme (at most
   alpha), power on planted effects at several n, attack-set false-kill rate on true
   effects (at most 0.15), and whether BH level holds on a family of correlated claims.
   Fixed seeds; document the numbers in the design doc §5.
3. **S3 (applicable attacks only).** Give each attack an explicit "applies" rule in
   code; not-applicable is recorded as `not_run: not_applicable` and never counts for
   or against. One coverage test per attack for applies and does-not-apply.

After each step: run the targeted tests, run the full suite in the background, open a
PR targeting the branch you started from, and write the PR body (purpose, files,
verification commands and results, limitations, contract or config impact).

When all three are done, summarise what is measured versus assumed, and list the open
questions from §7 of the design doc that still need the owner.
