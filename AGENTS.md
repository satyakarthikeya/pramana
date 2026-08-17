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

## 2. Model usage rules

- **DeepSeek V4 (API)** = verification gateway ONLY (falsification code generation, verification reasoning). Do not route routine tasks through it (cost) and do not replace it with a local model (trust thesis).
- **Gemma (local)** = schema inference, cleaning, classification, other cheap sub-agent tasks. Do not use it for verification.
- All LLM calls must be traced through **Langfuse**.

## 3. Statistics correctness rules (non-negotiable)

1. Falsification tests must be **actually executed** — never let an LLM "reason" its way to a p-value. If code fails to run, the insight is not verified (fail-closed → REJECT or RETRY, never PASS).
2. **Benjamini-Hochberg FDR correction** is applied across ALL hypotheses tested in a run, not per-insight. Collect all raw p-values first, correct once, then issue verdicts.
3. Thresholds (alpha, evidence score cutoffs) live in **one config file** — never hardcode them inline.
4. Random seeds for permutation/bootstrap must be **configurable and logged** for reproducibility.
5. Report effect sizes alongside p-values. A tiny p with a negligible effect size is not a strong finding.
6. Every verdict must produce a complete **proof object** (schema in `PROJECT.md` §5). No partial proof objects.

## 4. Execution safety rules

Falsification code is LLM-generated and then executed — treat it as untrusted:
- Execute in a **sandboxed/subprocess environment** with a timeout (via Celery worker).
- Whitelist imports (numpy, pandas, scipy, sklearn stats only). No network, no file writes outside a temp dir.
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

## 8. When uncertain

Priority order for resolving conflicts:
1. The prime directive (§0)
2. Statistics correctness (§3)
3. `SCOPE.md` boundaries
4. Existing interface contracts
5. Style preferences

If following an instruction would violate something higher on the list, flag it instead of complying.
