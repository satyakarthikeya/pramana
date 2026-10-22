# SCOPE.md — Current scope: ship and review V1

> One scope for the whole team. The old per-person scope files are gone.
> Context: `PROJECT.md`. Rules: `AGENTS.md`. Current state: `STATUS.md`.
> Final review: Tue 27 Oct 2026. Code freeze: end of Mon 26 Oct (fix only what a rehearsal breaks).

## 1. Goal

A stranger starts the app with one command, uploads a table, and gets verified findings with
proofs, rejected claims with reasons, and PASS-only memory, without help and without a
terminal beyond the start command.

Acceptance journey: open `http://localhost:8080` → upload (or try the sample) → watch stages
→ read verified findings → read rejected claims ("Not a finding" + reason) → browse/search
memory → upload a second dataset and see a past lesson offered as a hint → download JSON/CSV.

## 2. In scope

- Upload, cleaning, profiling, schema inference (rules)
- Claim proposal by DeepSeek, with the rule scan as an explicit offline mode
- The full verification gateway, proof objects, PASS-only memory
- The dashboard, export, README, one-command start
- Tests, lint, and the release checks in `STATUS.md`

## 3. Out of scope (do not build, do not present as features)

- A/B/C/D evaluation and benchmark runs
- Categorical-versus-categorical claims (Cramér's V stays unreachable)
- Bootstrap confidence intervals
- Celery/Redis and Docker/cloud deployment in the V1 run path
- Multi-user accounts, more than one run at a time
- Local-model (Gemma/Ollama) inference, episode selection

## 4. Boundaries that never move

- `memory_write ⟹ verdict == PASS`; fail closed; one BH family per run.
- No threshold, seed, permutation count, sandbox rule or verdict rule changes without
  the review required by `AGENTS.md` §8.10.
- Changes to contracts, `PROJECT.md`, `AGENTS.md`, `pyproject.toml` or shared config are
  called out in the PR (`AGENTS.md` §8.7).

## 5. Definition of done

- The acceptance journey works end to end, twice, on two datasets, from a clean clone.
- Every finding has a proof; no rejected claim is shown as a finding.
- Nothing but PASS reaches memory (test in the suite).
- Full suite and `ruff` green on `main`.
- README lets a new person succeed; limitations are visible in the product or README.

## 6. Limitations to state at review

- A well-powered association that is really a confound can PASS (no held-out split or adjustment).
- Effect floors do not separate truth from chance; the corrected q-value does. Small real effects PASS.
- Two-category claims are not testable.
- No confidence intervals on effect sizes.
- The trend test refuses datasets above 3,000 rows.
- One run at a time.
- The LLM generator has only one small live run (9 claims); its refusal rate at scale is unmeasured.
