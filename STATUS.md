# STATUS.md: where we are

> The single current-status file. Last rewritten 25 October 2026 on
> `chore/satya/cleanup-for-review`. Other status files under `docs/` are snapshots of one
> change or historical. No test count is kept here: run
> `python -m pytest --collect-only -q | tail -1` for the count and `python -m pytest`
> for the result. Next work is in `docs/ROADMAP.md`.

## 1. Branches

| Branch | State |
|---|---|
| `main` (`origin/main` at `bb5bb77`) | PR #31 merged on 24 Oct (UTC): analyst layer and gateway v3 F1-F7, S1-S8. Everything through PR #31 is on `main` |
| `chore/satya/cleanup-for-review` | this branch: docs rewrite, archive moves, lint and formatting, five unreferenced helpers removed. Not pushed as a PR yet |
| `origin/docs/satya/research-improvements` | one file, `docs/RESEARCH_improvements.md` (next steps and three evaluation experiments). Pushed, no PR, not merged |
| other `origin/feat/*`, `origin/docs/*` | merged through PRs #25-#31; check before deleting |

No pull request is open (`gh pr list`).

## 2. What is built (on `main`)

- **Upload and Report tab:** cleaning, profiling, schema inference, Data reader, sector
  match, Exact tier on the full table with story order and "what to watch" questions,
  code summary with an optional number-checked DeepSeek reword, Measured tier as a
  background task.
- **Checked claims tab:** split, four proposer engines (api default; planner; agent;
  deterministic), claim filters on the planner path, the v3 gateway (§2 of
  `PROJECT.md`), proofs with scheme, split, attacks, interval, power note, spec hash and
  look count; wording HELD UP / NOT ROBUST / "not enough evidence".
- **Ask tab:** chat with fixed tools; an inferential question is one gateway test (q = p),
  never written to memory.
- **Around it:** accounts, Memory page (PASS only), JSON/CSV export, Skeptic and
  Explainer, Langfuse tracing, fail-closed model calls.

## 3. Verified by running (dates from the source docs; not re-run for this file)

- Planted-fact recall of the Exact report: 7 of 7 (was 3 of 7) on six synthetic tables
  (`scripts/calibration/analyst_recall.py --top 8`; reproduced 25 Oct with `PYTHONPATH=src`).
- Gate report card at 100 replicates: see `PROJECT.md` §11.
- Live runs with DeepSeek and the planner (24-25 Oct, `docs/GATEWAY_V3_STATUS_AND_SIGNOFF.md`
  §4): NHANES demo 3 held up, 3 rejected (one FRAGILE: HbA1c effect fell from +0.30 to
  +0.11 with age held fixed), 259 s; synthetic financial-year table 3 held up, 2 rejected.
  The planner varies, so counts are not a regression test of specific claims.
- Real retail data (UCI Online Retail II, customer x month x country): Report checked in
  the running app (`docs/ANALYST_LAYER_STATUS.md`).
- Full suite: `python -m pytest` exited 0 (no failures) on this branch at `4eaa60b`,
  25 Oct; later commits are docs only. Get the count with the collect-only command above.

## 4. Not verified

- Docker for gateway v3 and the analyst layer (never run); the sandbox memory limit
  inside the image.
- Web: no unit tests exist; keyboard-only, 800 px, grayscale and phone-width passes.
- mypy on the newer modules.
- BH on correlated claim families; attack false-kill on real tables; gate vs no gate.

## 5. Known limits and open items

- **Generator default mismatch:** project default is `template` (`configs/verification.yaml`,
  `configs/v1.yaml`, AGENTS.md §2), but `.env.example:8` and
  `docker/docker-compose.yml:17,61` select `llm`. Copying `.env.example` makes
  `python -m pramana` run model-written tests. Set `PRAMANA_VERIFICATION_GENERATOR=template`.
- **Engine:** the default proposer is `api`; every documented live run used `planner`,
  which is selected only with `PRAMANA_ANALYSIS_ENGINE=planner`.
- **3,000-row trend ceiling:** above 3,000 rows every trend claim is dropped with a
  recorded reason, even when its test would run on period means; chat refuses trends
  there. Retail tables with 24 months are also too short for a trend (12 confirmation
  periods, minimum 20).
- **Planner non-determinism:** different claims on different runs.
- **Report reword fallback:** on the retail table the DeepSeek reword fell back to the
  code text ("a number that is not in the figure"); not investigated.
- **Sign-off sheet:** rows 1-9 of `docs/GATEWAY_V3_STATUS_AND_SIGNOFF.md` §5 are unticked
  although the code is merged.
- **Student registration numbers** are in 15 tracked files (`git grep -l "CB.AI.U4AID"`):
  `requirements/*.txt` headers, eight `src/pramana/*/OWNERSHIP.md`, `docs/team/`,
  `docs/archive/`.
- **Evaluation harness** is reachable only from tests (`PROJECT.md` §6).
- **Measured** needs several numeric columns; on the customer x month retail table only
  two exist, so models, segments and components do not run.
- **Lint:** `ruff check .` reports 12 findings at `e927a5d` (before this docs
  rewrite; long lines in `planner.py`, `attacks/runner.py`, `refuter.py`; an unused
  variable in `gateway.py:657`; unsorted imports in `gateway.py`; a loop-variable
  closure in `tests/unit/verification/test_refuter.py`). The verification files need the
  owner's review.
- **Not detected:** a partial last period (a table that ends mid-month).
- Memory is shared across accounts; one run at a time.

## 6. Stale text in files outside this docs change

Left for a follow-up (they are outside this change's file list):

| File | Stale claim | Truth |
|---|---|---|
| `README.md:3` | "Self-evolving" | memory only offers PASS lessons as hints |
| `README.md:5,11` | "reports only findings that pass"; "default rule scan" | three levels; proposer default `api` |
| `README.md:27,55` | DeepSeek V4 writes the test | `template` is the default |
| `README.md:32` | `dashboard/` package | does not exist; UI is `web/` |
| `README.md:129-133` | engine table without `planner` | `planner` exists |
| `README.md:197-202` | no held-out replication, no CIs, tables refused above 3,000 rows | split, interval and trend-drop exist |
| `tests/conftest.py:20` | shipped default is `llm` | `template` |
| `docs/GATEWAY_V3_STATUS_AND_SIGNOFF.md:12,27,96` | nothing pushed; PR 29 open; 5000 resamples | merged; 1,000 resamples |
| `docs/DESIGN_verification_gateway_v3.md:3` | "Nothing here is built" | S1-S8 built |
| `docker/README.md:49` | live profile selects `llm` | default should be `template` |
| `web/src/components/Results.tsx:369` | heading "Verified findings" | badges say HELD UP |
| `docs/README.md` (Current table) | lists `V1.md` as current | V1-era plan; historical |

## 7. Before the 27 Oct review

- [ ] Open the cleanup PR and get it reviewed.
- [ ] Confirm the venv imports this tree (`python -c "import pramana; print(pramana.__file__)"`)
      and rebuild `web/dist`.
- [ ] Run with `PRAMANA_VERIFICATION_GENERATOR=template` and `PRAMANA_ANALYSIS_ENGINE=planner`;
      check both on `/api/system`.
- [ ] Owner signs or discloses the sign-off sheet.
- [ ] Human rehearsal of the acceptance journey (`SCOPE.md` §1).
- [ ] Report text written by humans (`AGENTS.md` §7).
