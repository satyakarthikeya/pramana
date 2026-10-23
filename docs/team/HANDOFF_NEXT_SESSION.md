# Handoff: continue PRAMANA from here (written 23 Oct 2026)

Read this whole file first. It is the state of the project at the end of a long session, so a
new session can continue without guessing. When it conflicts with the code, the code wins.

## 0. First five minutes

1. Read `AGENTS.md` (rules), `PROJECT.md`, `SCOPE.md`, `STATUS.md`, `docs/ANALYSIS_AGENT.md`,
   and `.claude/skills/pramana-ui/SKILL.md` (UI rules; load it before any frontend work).
2. `git status` and `git branch --show-current`. You should be on `feat/team/workspace-ui`
   with about 60 **uncommitted** files. Nothing from this session is committed. Do not lose
   them: finish Section 4 (verify, then commit) before starting new work.
3. Run the full suite with the real exit status (a past run reported "0" because of `| tail`):

   ```bash
   .venv/Scripts/python.exe -m pytest -p no:warnings -q 2>&1 | tail -6; echo "exit=${PIPESTATUS[0]}"
   ```
   It takes about 7 minutes; run it in the background. Last confirmed state (23 Oct 2026): the
   full suite passed with pytest's own exit status 0, and `ruff check .` was clean, after two
   tests that checked deliberately changed behaviour were updated (`test_episode_workflow.py`,
   `test_agent.py`). Re-run it anyway after any change; mypy has not been run on the new modules.

## 1. What PRAMANA is

A data-analysis platform. A signed-in user uploads a CSV/XLSX; code profiles it and a Data
Reader notes what is in it; an Analyst proposes claims; a verification gateway runs real
permutation tests on every claim, applies one Benjamini-Hochberg correction per run and a
deterministic gate; only PASS findings are shown as findings and only PASS reaches memory.
Rejected claims stay visible with the reason. Core principle: models propose and write
code, **code decides**. Invariant: `memory_write => verdict == PASS` (AGENTS.md section 0).

## 2. Who the user is and how they work (important)

- Capstone team AB-07 (Amrita). Non-expert in some areas; wants plain-language explanations,
  decisions made for them, and **no mistakes**. They said "make sure everything runs end to end".
- Wants a **real** product, **no mock data** anywhere in the product. Sample data exists only
  in `tests/fixtures/sample_data.py`.
- Everything runs in **Docker** (they have no local database). Node is allowed for the UI.
- UI uses the Calm-based skill in `.claude/skills/pramana-ui` (fonts they liked: Inter,
  Source Serif 4, JetBrains Mono). No AI-slop (gradients, shadows, emoji, purple/blue).
- Use subagents for independent review/QA (they approved it). One independent review already
  found a critical sandbox bypass; keep doing a review before declaring anything done.
- Be honest about what was and was not verified. Never print secrets. Never delete their
  real account/data. Report failures plainly (a false "passed" happened once; do not repeat).
- They decided: per-user verified memory and "signing" polish come **later**.

## 3. State of the code (all uncommitted on `feat/team/workspace-ui`)

Built and tested this session:

| Area | Where | Notes |
|---|---|---|
| Datasets: upload once, profile with code only | `src/pramana/api/datasets.py`, `routes/datasets.py` | stored under `data/api/datasets/<id>/`; stored briefs from older versions are dropped and rebuilt (never fatal) |
| Accounts (email + password) | `src/pramana/api/auth.py`, `routes/auth.py`, `deps.py` | scrypt hashes, server-side sessions, HttpOnly cookie, same-origin check, per-address limits, atomic first account; first account claims pre-existing data |
| Per-user ownership | `repository.py`, `datasets.py`, routes | datasets and runs filter by owner; cross-user ids return 404 |
| Chart data (descriptive only) | `src/pramana/api/charts.py` | per-claim scatter/groups, per-dataset overview + correlations |
| Data Reader | `src/pramana/analysis/reader.py`, `codebook.py` | counted facts: missing codes, outliers, NHANES labels; code only, no model |
| Analysis workspace | `src/pramana/analysis/workspace/` | tools (`describe`, `compare_groups`, `relate`, `trend`, `missingness`, `scan_pairs`), ledger, bounded Python sandbox, agent loop |
| Exploration disclosure | `analysis/exploration.py`, `hypotheses/base.py` scan counter | results show "looked at / proposed / tested" |
| System status | `routes/system.py` | engine, blockers (names only, never values) |
| Web UI | `web/` (Vite + React + TS) | app shell, dataset Overview/Findings, proof drawer, charts, sign-in; built by `docker/Dockerfile.web`, served by nginx |
| Docker | `docker/Dockerfile.api`, `Dockerfile.web`, `docker-compose.yml`, `docker-compose.offline.yml`, `nginx.conf`, `requirements/runtime.txt` | API image slimmed 2.01 GB -> 1.38 GB; embedding model baked in; API port not published |

Engines (`PRAMANA_ANALYSIS_ENGINE`): `deterministic` (rule scan, no model), `api` (model proposes
from summaries), `agent` (model + tools). Verification generator: `template` (offline) or `llm`.

### Run it

```bash
# offline (no keys needed): rule scan + built-in test templates
docker compose -f docker/docker-compose.yml -f docker/docker-compose.offline.yml up --build -d
# open http://localhost:3000
```
Stop with `... down`. The API is only reachable through nginx on port 3000.

### The user's real data (do not touch)

The Docker volume has the user's real account (an `sat***@gmail.com` account) owning one dataset
(`demo_nhanes_small.csv`) and 3 runs. To test, create a **throwaway account**, then remove only
that account and its rows/files afterwards (the pattern used before: a short Python script
run with `docker exec -i pramana-dev-api-1 python -`, deleting rows where `owner_id` is the QA
user, plus `data/api/datasets/<id>` and `data/runs/<id>` folders). Always check
`SELECT COUNT(*) FROM users` shows 1 afterwards.

## 4. Do this first: finish Phase 3 properly

1. Confirm the full suite is green (command in Section 0) and `ruff check .` is clean.
2. Run mypy on the new modules if time allows (`mypy` was never run on them).
3. Commit in logical pieces on `feat/team/workspace-ui` (AGENTS.md section 8: small commits,
   Conventional Commit subjects, no secrets, never commit `data/`). Suggested order:
   backend datasets+charts, auth+ownership, workspace+reader+agent, web UI, docker, docs/skill.
   Do not push or open a PR unless the user asks. `.claude/skills/pramana-ui/` is untracked and
   should be committed with the UI.
4. In the PR description (when asked) call out shared files per AGENTS.md section 8.7:
   `pyproject.toml` (dashboard package entry removed), `requirements/runtime.txt` (new),
   Dockerfiles and compose files, `configs/analysis.yaml` (workspace section),
   `configs/v1.yaml` (sample keys removed), `proposer_config.py` (new `agent` engine),
   `hypotheses/base.py` + three strategy files (scan counter, no behaviour change),
   deletion of the old dashboard and `scripts/check_v1_browser.mjs`.

## 5. Open decisions and known gaps (state these to the user, do not hide)

1. **Live DeepSeek is unverified.** All model-driven parts (`api`/`agent` engines, `llm`
   generator) need `DEEPSEEK_API_KEY` **and** Langfuse keys (`LANGFUSE_PUBLIC_KEY`,
   `LANGFUSE_SECRET_KEY`) because every model call must be traced (AGENTS.md section 2;
   `complete_chat` refuses without Langfuse). The user's `.env` has the DeepSeek key but empty
   Langfuse keys. The agent loop is tested only against scripted replies. First action when keys
   exist: run `PRAMANA_ANALYSIS_ENGINE=agent` once on `data/demo_nhanes_small.csv`, record tokens,
   claims and cost, and check the transcript `data/runs/<run>/agent_transcript.json`.
2. **Verified memory is shared across accounts** (`routes/memory.py`; lessons also feed
   `lesson_hints` into the next user's prompt). Real cross-user leak. User deferred it; do it
   before more than one person uses a server. Needs an owner field on lessons.
3. **Python workspace tool is OFF by default** (`workspace.sandbox.enabled: false`). A review
   proved the static checks alone were bypassable (`pd.io.common.os.system`); a runtime audit
   hook plus module-hop name blocks were added and the exploits are regression tests, but it is
   not a proof. Enable only for single-user installs or inside the isolated worker.
4. **Exploration is disclosed, not counted in the BH family.** Changing the family is a
   statistics-rule change (AGENTS.md section 3): needs the verification owner. Options: count all
   examined hypotheses, or cap what the analyst may examine. Hold-out split not built.
5. First sign-up on an empty server always succeeds even with `PRAMANA_ALLOW_SIGNUP=0`
   (bootstrap). Do not expose a fresh server publicly.
6. Unauthenticated multipart uploads may be spooled before the 401 (bounded by nginx 100 MB).
7. Per-run cost controls only; no per-dataset spending cap, no cross-run cache.
8. `AGENTS.md` section 8.10 still talks about module owners; old per-person scope files are gone.
   Code comments citing them were left alone. `docs/V1.md` and the V1 test log are historical.
9. Evaluation harness (A/D conditions) and the Celery worker path exist but are not on the V1
   path; deleting them was proposed and **not** approved.

## 6. Remaining phases

### Phase 4: Chat agent ("talk to your data")

Goal: on a dataset, a user asks questions in plain language and gets answers they can trust.

- UI: a third tab **Ask** on the dataset page (do not add placeholder UI before it works).
  Conversation is stored per user and dataset (SQLite, same file as runs).
- Backend: `POST /api/datasets/{id}/chat` (consider server-sent events for streaming).
  Reuse `Workspace` tools and the same hard budgets pattern; add per-message budgets in
  `configs/analysis.yaml` (`workspace.chat`).
- Answer types, always labelled in the UI:
  - **Descriptive** (counts, means, medians, group summaries, missingness): computed exactly by
    tools; each answer cites the tool call id and can show the table or chart that produced it.
  - **Inferential** ("does X affect Y?"): the agent proposes a structured claim; code runs it
    through the **gateway** and the answer shows **Verified** or **Rejected** with the proof.
    If it is not sent to the gateway it must say **Exploratory, not verified** and must never
    state a significance.
- Multiple testing: every chat-asked claim is another test. Keep a per-dataset **testing ledger**
  (what was tested, when, from which question) and show the running count; label chat claims
  "asked after seeing results". Whether they join an existing BH family is an open statistics
  decision (Section 5.4); implement the ledger and disclosure first, ask before changing the gate.
- Safety: column names, labels, cell values and the user's text are untrusted data. The model
  never computes a number or writes a verdict. Fail closed without DeepSeek+Langfuse with an
  explicit message. Tests use scripted replies; add prompt-injection tests (a column named
  "ignore previous instructions").
- Needs AGENTS.md section 2 wording for the new role and verification-owner review.

### Phase 5: Skeptic and Explainer (not started; user asked to stop at Phase 3 then 4 after)

- **Skeptic**: after the gate, reviews PASS findings for likely confounds using descriptive tools
  (for example a third variable related to both). Output is caveats and suggested follow-up
  claims for a **next** run. It can never change a verdict or resubmit within a run (AGENTS.md:
  one run, one family, tested once).
- **Explainer**: writes plain-language summaries of findings. Code must check that every number
  it cites equals the proof object field; any mismatch fails closed and falls back to the
  template sentence.
- Later: a lesson-curator agent; per-user memory (Section 5.2) should come before it.

## 7. Practices that avoid repeating mistakes

- **Branching:** one task, one branch (`<type>/<owner>/<task>`); never commit to `main`.
- **Tests first for statistics/safety code**; known-answer tests; reproduce any reviewer claim
  yourself before and after fixing.
- **Do not run `ruff format` on whole packages**; it reformatted other people's files once and
  had to be reverted. Format only the files you wrote.
- **Shell quoting:** long Python edits via `python - <<'EOF'` broke on quotes and `\n` more than
  once. Write the edit script to a file with the Write tool, then run it, and assert each
  `old in text` before replacing.
- **Windows paths:** `/tmp` in Git Bash is not the same as Python's `/tmp`; use the scratchpad.
  Use `MSYS_NO_PATHCONV=1` with `docker exec` paths.
- **Browser pane:** screenshots crop to about 800 px wide; set `resize_window` to 800x640 and
  scroll with JavaScript. The page caches aggressively; append `?v=N` to URLs. Reset the
  viewport with `preset: "desktop"` afterwards.
- **A hung `docker compose build`** is normally the network; cold builds took about 12 minutes,
  warm rebuilds about 30 seconds.
- **Changing a stored data format** (a Pydantic Literal, a field) can break saved rows. Make
  loaders tolerant and add a test with an old-format row (this caused a 500 on the dataset list).
- Run anything long with `run_in_background` and wait for the completion notification; check the
  real exit status, not the pipe's.
- Update `STATUS.md` and this file when a phase changes state.

## 8. Quick verification checklist (use before saying "done")

- [ ] Full pytest green with real exit status; `ruff check .` clean.
- [ ] Offline Docker stack up; sign up a throwaway account; upload `data/demo_nhanes_small.csv`;
      the Overview shows the Data Reader brief; Analyse completes; Findings show 3 verified and
      2 rejected, charts, proof drawer, and the "How these claims were found" panel.
- [ ] Second account cannot see the first's datasets, runs, results or exports (404).
- [ ] No horizontal scroll at 390 and 800 px; keyboard reaches every control.
- [ ] Throwaway accounts and their data removed; the real account untouched.
- [ ] An independent review (subagent, read-only) of the new code, with exploits reproduced.
