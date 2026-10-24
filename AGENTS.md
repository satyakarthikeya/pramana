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

- **DeepSeek-only profile (user requested 21 October 2026)**: DeepSeek is the only generative provider. In the gateway the DEFAULT is a vetted test per claim type and scheme rendered by code (`llm.generator: template`, decided 24 October 2026 after a live run lost claims to model-written code); when `llm.generator: llm` is selected explicitly, its role is ONLY writing falsification code (`falsify(frame)`), which may import only `numpy`, `pandas` and `pramana.verification.stats` and must obtain every p-value and effect size from that library. DeepSeek never supplies a statistic, q-value or verdict as evidence.
- **Analysis LLM** (DeepSeek API, separate role/prompt) = proposes STRUCTURED candidate claims only (`claim_type`, `variables`, direction, reference group). Code renders the claim sentence from a hedged template; the model never authors `claim` text. Nothing it outputs is passed to the gate as evidence, and `analysis_evidence` never carries a p-value, q-value or verdict.
- **Routine operations** remain deterministic where implemented: schema heuristics, cleaning, lesson formatting. No Gemma/Ollama inference path remains. An optional semantic-refiner interface is not an implemented model call. MiniLM embeddings for memory search are not a generative LLM and remain local. Any future model-assisted routine operation must use explicitly configured DeepSeek, never edit data directly, and trace its calls.
- **Chat assistant** (DeepSeek, separate role/prompt, "talk to your data"): looks at the table through the fixed descriptive workspace tools, then either answers or proposes ONE structured claim. It never computes a number, writes a claim sentence, labels its own answer or supplies a verdict. Code shows its wording only if every number matches a cited tool result and no verdict or causal vocabulary appears; otherwise the wording is withheld and the tool results are shown. An inferential question is answered only by the verification gateway, as its own family of one under the same run slot as analysis runs. Its reply is rendered by code from the proof, disclosed as asked after seeing results and not corrected for earlier tests, counted in a per-dataset ledger, and never written to memory (`memory_write ⟹ verdict == PASS` is unchanged). It fails closed without DeepSeek and Langfuse, and traces each message under its own UUID. Whether chat claims should ever join an existing BH family is a statistics decision for the verification owner (§8.10), not made here.
- **Explainer** (code by default; DeepSeek only when `advisory.explainer.engine` is `api`): writes a plain-language sentence for each PASS finding, after the gate. The default sentence is written by code from the proof's own numbers. A model sentence is kept only if every number in it matches a number displayed with the finding (q, raw p, effect, rows, claims in the run, alpha; never the test code, seed or ids), it uses no verdict, causal or evidence vocabulary and names no other column; code appends the facts line and the association-not-cause disclaimer. Any failure falls back to the code sentence and the fallback is recorded and shown. It runs once per run, traced under the run's UUID, and has no path to a proof object, the run's family or memory. The **Skeptic** that sits beside it is code only (no model): it computes rank partial associations from the table to flag a column that may account for part of a finding, as descriptive caveats and questions for a NEXT run, never a verdict, a claim in this run, or a memory write. Its thresholds live in `configs/analysis.yaml` (`advisory.skeptic`) and need the verification owner's review (§8.10).
- **Sector reader and report writer** (DeepSeek, separate roles and prompts, on the Exact tier only; added 24 October 2026). The sector reader names one sector pack from column NAMES, detected roles and codebook labels, never a value; code accepts only a loaded pack or `general` and fills the roles itself; a model problem falls back to the rule detector and is recorded in the match's reasons and the log (`computed.sector_engine`). The report writer may choose up to five code-ranked Exact figures and reword them; a line is kept only if its figure id was offered, every number in it appears in that figure, and it uses no verdict, causal or universal wording; otherwise the code-written summary is shown with the reason (`computed.summary_engine`). It sees figures, never table rows, and runs after the upload response. Both are traced under the dataset's id and have no path to a claim, the gateway or memory.
- **No silent model substitution.** A run configured for a model either gets that model's output or fails closed (NOT_TESTABLE / a recorded error). The template generator is chosen explicitly in config, never used as a quiet fallback.
- All LLM calls must be traced through **Langfuse**, under the run's `run_id`.
  The historical local-proposer exception does not authorize untraced hosted calls.
  DeepSeek calls require valid Langfuse credentials and fail closed without them.
  Local run artifacts remain an additional audit record, not a tracing fallback.

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
