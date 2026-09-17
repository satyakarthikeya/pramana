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

## 2. Git collaboration, commits, and pull requests

`main` is the shared, protected integration branch. It must always be in a
reviewable, testable state. No person or agent may commit directly to it.

1. **One task, one branch.** Before editing, create a branch from the latest
   `origin/main`. Use `codex/<owner>/<short-task>` for agent-created branches
   (for example, `codex/satya/implement-memory-guard`). Human-created branches
   may use the same format or `feat/<owner>/<short-task>`.
2. **Never mix workstreams.** A branch and its pull request contain one logical
   change only. Do not add cleanup, formatting sweeps, dependency upgrades, or
   another member's work to an unrelated branch.
3. **Commit small, meaningful checkpoints.** Each commit must be buildable where
   practical and use a Conventional Commit-style subject:
   `feat(verification): add memory guard`, `fix(executor): reject relative imports`,
   `test(stats): cover null permutation case`, or `docs: clarify PR policy`.
   Keep the subject imperative and under 72 characters. Explain any dependency,
   config, contract, or statistical-decision change in the commit body.
4. **Verify before committing.** Run the targeted pytest files for the changed
   component. Run the full suite when feasible; otherwise state clearly in the PR
   what was run and what was not. A failing test, lint error, or unreviewed change
   must not be committed as complete work.
5. **Never commit secrets or raw data.** API keys, `.env` files, credentials,
   generated local databases, and raw datasets stay out of Git. Do not stage
   another contributor's uncommitted files.
6. **Contracts and shared configuration need coordination.** Changes to
   `src/pramana/contracts/`, `PROJECT.md`, `AGENTS.md`, `OWNERSHIP.md`,
   `pyproject.toml`, or shared requirements/configuration must be explicitly
   called out in the PR and announced to affected module owners before merging.
7. **Every branch merges through a pull request.** Push the branch and open a PR
   targeting `main`; direct pushes, force-pushes to `main`, and merge commits made
   locally into `main` are forbidden. Do not merge your own PR without the required
   review.
8. **PR description is mandatory.** Include: purpose and scope, files/modules
   affected, verification commands and results, any limitations or follow-up work,
   and any contract/config/dependency impact. Link the relevant issue/task when one
   exists.
9. **Review follows ownership.** The relevant module owner reviews code in their
   directory. Shared-contract or cross-module changes require review from every
   affected owner. Anything that can affect `memory_write => verdict == PASS`,
   p-values, FDR correction, or sandbox safety requires the verification owner’s
   approval.
10. **Merge only green, current PRs.** Resolve review comments, rebase or update
    from current `main` when needed, confirm CI/tests pass, then use the repository's
    approved PR merge method. Delete the merged feature branch after confirming the
    change is present in `main`.

## 3. Model usage rules

- **DeepSeek V4 (API)** = verification gateway ONLY (falsification code generation, verification reasoning). Do not route routine tasks through it (cost) and do not replace it with a local model (trust thesis).
- **Gemma (local)** = schema inference, cleaning, classification, other cheap sub-agent tasks. Do not use it for verification.
- All LLM calls must be traced through **Langfuse**.

## 4. Statistics correctness rules (non-negotiable)

1. Falsification tests must be **actually executed** — never let an LLM "reason" its way to a p-value. If code fails to run, the insight is not verified (fail-closed → REJECT or RETRY, never PASS).
2. **Benjamini-Hochberg FDR correction** is applied across ALL hypotheses tested in a run, not per-insight. Collect all raw p-values first, correct once, then issue verdicts.
3. Thresholds (alpha, evidence score cutoffs) live in **one config file** — never hardcode them inline.
4. Random seeds for permutation/bootstrap must be **configurable and logged** for reproducibility.
5. Report effect sizes alongside p-values. A tiny p with a negligible effect size is not a strong finding.
6. Every verdict must produce a complete **proof object** (schema in `PROJECT.md` §5). No partial proof objects.

## 5. Execution safety rules

Falsification code is LLM-generated and then executed — treat it as untrusted:
- Execute in a **sandboxed/subprocess environment** with a timeout (via Celery worker).
- Whitelist imports (numpy, pandas, and `pramana.verification.stats` only — the vetted library internally uses scipy, generated code may not import it directly). No network, no file writes outside a temp dir.
- Cap memory/CPU per execution.
- On timeout or crash: log to Langfuse, mark the test as failed, fail-closed.

## 6. Code style

- Python 3.11+, type hints on all public functions.
- Pydantic models for every inter-module payload (candidate insight, proof object).
- Docstrings state WHAT the function guarantees, not just what it does.
- Tests: pytest. Statistical functions get tested against known-answer cases (e.g. a planted null relationship must yield high p; a planted strong effect must yield low p).
- Logging: structured (JSON), include `insight_id` in every log line inside the gateway.

## 7. Data rules

- Allowed datasets: NHANES, NFHS-5, other open-access data. **MIMIC-IV is forbidden** (license conflict).
- Never commit raw datasets to the repo — data lives in a gitignored `data/` dir.
- Benchmark must exclude famous datasets (Iris, Titanic, etc.) — contamination screening.

## 8. Report / documentation rules

- Generated code comments are fine; generated REPORT prose is constrained: the written capstone report must stay **under 20% AI-generated** and **under 15% plagiarism**. When asked to draft report text, produce outlines/bullet points for humans to write up, unless explicitly told otherwise.

## 9. When uncertain

Priority order for resolving conflicts:
1. The prime directive (§0)
2. Statistics correctness (§4)
3. `SCOPE.md` boundaries
4. Existing interface contracts
5. Git collaboration (§2)
6. Style preferences

If following an instruction would violate something higher on the list, flag it instead of complying.
