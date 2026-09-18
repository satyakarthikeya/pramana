# AGENTS.md — Rules for AI coding agents working on PRAMANA

> Applies to ANY coding agent (Claude Code, Cursor, Copilot, Aider, Windsurf, etc.).
> Read `PROJECT.md` first for context, `SCOPE.md` for the current work scope.

## 0. Prime directive

**Never create a path where an unverified insight reaches the user or ChromaDB.**
Every code change must preserve the invariant: `memory_write ⟹ verdict == PASS`.
If a change would weaken this, stop and flag it instead of implementing it.

## 1. General rules

1. **Read before writing.** Inspect existing module interfaces before generating code. Do not invent new schemas when a contract already exists in `PROJECT.md` §5.
2. **Small, reviewable diffs.** One logical change per commit/edit. No drive-by refactors of other members' modules.
3. **Stay in scope.** Only touch files inside the scope defined in `SCOPE.md` unless explicitly asked. Other modules belong to other team members.
4. **No silent dependency changes.** Adding a pip package? Add it to requirements, and note WHY in the commit message.
5. **Ask, don't assume**, when a requirement is ambiguous — especially anything touching statistics correctness or the PASS/REJECT decision.
6. **Never renumber a section of this file.** Section numbers are cited by code,
   configs, tests and every other member's scope file (`AGENTS.md §3.3` in
   `configs/verification.yaml`, `§4` in `SCOPE_B_Karthikeya.md`, `§6` in `.gitignore`,
   and dozens more). Inserting a section in the middle silently redirects every one of
   those citations to the wrong rule, and nothing fails loudly when it happens. Add new
   sections at the END, before §9.

## 2. Model usage rules

The principle behind every rule below: **models propose and write code; code decides.**
Where each model sits in the flow, and what is built, is in `PROJECT.md` §2.

- **DeepSeek V4 (API)** = verification gateway ONLY, and inside it ONLY to write falsification code (`falsify(frame)`). That code may import only `numpy`, `pandas` and `pramana.verification.stats`, and must obtain every p-value and effect size by calling that library. DeepSeek never computes, estimates or reports a statistic, a q-value or a verdict. Do not route routine tasks through it (cost) and do not replace it with a local model (trust thesis).
- **Analysis LLM** (Gemma or an API model, set in config) = proposes STRUCTURED candidate claims only (`claim_type`, `variables`, direction, reference group). Code renders the claim sentence from a hedged template; the model never authors `claim` text. Nothing it outputs is passed to the gate as evidence, and `analysis_evidence` never carries a p-value, q-value or verdict.
- **Gemma (local)** = schema inference and cleaning help (label a column, suggest a step that code applies and logs), lesson abstraction, other cheap sub-agent tasks. It never edits data directly. Do not use it for verification.
- **No silent model substitution.** A run configured for a model either gets that model's output or fails closed (NOT_TESTABLE / a recorded error). The template generator is chosen explicitly in config, never used as a quiet fallback.
- All LLM calls must be traced through **Langfuse**, under the run's `run_id`.

## 3. Statistics correctness rules (non-negotiable)

1. Falsification tests must be **actually executed** — never let an LLM "reason" its way to a p-value. If code fails to run, the insight is not verified (fail-closed → REJECT or RETRY, never PASS).
2. **Benjamini-Hochberg FDR correction** is applied across ALL hypotheses tested in a run, not per-insight. Collect all raw p-values first, correct once, then issue verdicts.
3. Thresholds (alpha, evidence score cutoffs) live in **one config file** — never hardcode them inline.
4. Random seeds for permutation/bootstrap must be **configurable and logged** for reproducibility. When an LLM writes the test code, reproducibility means re-executing the stored `falsification_code` with the logged seed, which must give identical numbers; regenerating the code is not expected to.
5. Report effect sizes alongside p-values. A tiny p with a negligible effect size is not a strong finding.
6. Every verdict must produce a complete **proof object** (schema in `PROJECT.md` §5). No partial proof objects.

## 4. Execution safety rules

Falsification code is LLM-generated and then executed — treat it as untrusted:
- Execute in a **sandboxed/subprocess environment** with a timeout (via Celery worker).
- Whitelist imports (numpy, pandas, and `pramana.verification.stats` only — the vetted library internally uses scipy, generated code may not import it directly). No network, no file writes outside a temp dir.
- Cap memory/CPU per execution.
- On timeout or crash: log to Langfuse, mark the test as failed, fail-closed.

## 5. Code style

- Python 3.11+, type hints on all public functions.
- Pydantic models for every inter-module payload (candidate insight, proof object).
- Docstrings state WHAT the function guarantees, not just what it does.
- Tests: pytest. Statistical functions get tested against known-answer cases (e.g. a planted null relationship must yield high p; a planted strong effect must yield low p).
- Logging: structured (JSON), include `insight_id` in every log line inside the gateway.

## 6. Data rules

- Allowed datasets: NHANES, NFHS-5, other open-access data. **MIMIC-IV is forbidden** (license conflict).
- Never commit raw datasets to the repo — data lives in a gitignored `data/` dir.
- Benchmark must exclude famous datasets (Iris, Titanic, etc.) — contamination screening.

## 7. Report / documentation rules

- Generated code comments are fine; generated REPORT prose is constrained: the written capstone report must stay **under 20% AI-generated** and **under 15% plagiarism**. When asked to draft report text, produce outlines/bullet points for humans to write up, unless explicitly told otherwise.

## 8. Git collaboration, commits, and pull requests

`main` is the shared, protected integration branch. It must always be in a
reviewable, testable state. No person or agent may commit directly to it.

1. **One task, one branch.** Branch before editing. Name branches
   `<type>/<owner>/<short-task>`, reusing the Conventional Commit types from rule 4:
   `feat/satya/memory-guard`, `fix/satya/executor-relative-imports`,
   `docs/team/pr-policy`. The convention is identical for humans and coding agents.
   Which tool typed the code belongs in the commit trailer, not the branch name: a
   tool-specific prefix stops being true the moment the tool changes, and it tells a
   reviewer nothing they need in order to review.
2. **Branch from `origin/main` — unless the work depends on unmerged work.** Most
   branches start at the latest `origin/main`. When a task genuinely builds on a
   branch that has not merged yet, branch from THAT branch, say so in the PR, and
   merge in dependency order. A PR's diff is computed against its merge base, so
   merging out of order silently drags the parent's commits through the child's
   review, and nobody reads them twice.
3. **Never mix workstreams.** A branch and its pull request contain one logical
   change only. Do not add cleanup, formatting sweeps, dependency upgrades, or
   another member's work to an unrelated branch.
4. **Commit small, meaningful checkpoints.** Each commit must leave the suite
   runnable — no half-applied rename, no import that resolves only in the next
   commit — and use a Conventional Commit-style subject:
   `feat(verification): add memory guard`, `fix(executor): reject relative imports`,
   `test(stats): cover null permutation case`, or `docs: clarify PR policy`.
   Keep the subject imperative and under 72 characters. Explain any dependency,
   config, contract, or statistical-decision change in the commit body.
5. **Verify before committing.** Run the targeted pytest files for the changed
   component, and the full suite. The full suite takes about two minutes, so "not
   feasible" is not a reason — if you skip it, say so in the PR and say why. A
   failing test or lint error must not be committed as complete work.
6. **Never commit secrets or raw data.** API keys, `.env` files, credentials,
   generated local databases, and raw datasets stay out of Git. Do not stage
   another contributor's uncommitted files.
7. **Contracts and shared configuration need coordination.** Changes to
   `src/pramana/contracts/`, `PROJECT.md`, `AGENTS.md`, `OWNERSHIP.md`,
   `pyproject.toml`, or shared requirements/configuration must be explicitly
   called out in the PR and announced to affected module owners before merging.
8. **Every branch merges through a pull request.** Push the branch and open a PR
   targeting `main`; direct pushes, force-pushes to `main`, and merge commits made
   locally into `main` are forbidden. Do not merge your own PR without the required
   review.
9. **PR description is mandatory.** Include: purpose and scope, files/modules
   affected, verification commands and results, any limitations or follow-up work,
   and any contract/config/dependency impact. Link the relevant issue/task when one
   exists.
10. **Review follows ownership, with one unblocking exception.** The relevant module
    owner reviews code in their directory; shared-contract or cross-module changes
    need every affected owner. If an owner is unavailable for more than one working
    day, any other member may review and merge — EXCEPT for anything touching
    `memory_write => verdict == PASS`, p-values, FDR correction, or sandbox safety,
    which always requires the verification owner's approval. A four-person team
    cannot afford a rule that blocks on one person, and it cannot afford a gate that
    anyone can open either.
11. **Merge only green, current PRs.** Resolve review comments, rebase or update
    from current `main` when needed, confirm CI/tests pass, then use the repository's
    approved PR merge method. Delete the merged feature branch after confirming the
    change is present in `main`.

## 9. When uncertain

Priority order for resolving conflicts:
1. The prime directive (§0)
2. Statistics correctness (§3)
3. `SCOPE.md` boundaries
4. Existing interface contracts
5. Git collaboration (§8)
6. Style preferences

If following an instruction would violate something higher on the list, flag it instead of complying.
