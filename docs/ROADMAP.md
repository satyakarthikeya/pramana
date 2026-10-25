# ROADMAP

> What is in review, what comes next and in what order, and the rules any session must
> follow. State today: `../STATUS.md`. Architecture: `../PROJECT.md`. Rules:
> `../AGENTS.md`. Written 25 October 2026. Effort figures marked [estimate] are guesses
> for one developer with an assistant; others are taken from the plan they cite.

## 1. NOW (in review)

PR #31 (analyst layer and gateway v3) is **merged** to `main` (`bb5bb77`). What is in
flight:

| Item | State | Next step |
|---|---|---|
| Cleanup branch `chore/satya/cleanup-for-review` | docs rewrite (PROJECT, SCOPE, STATUS, CLAUDE.md, this file), archive moves, lint and formatting, five unreferenced helpers removed. No PR yet | push, open the PR to `main`, fill the description (AGENTS.md §8.9), call out PROJECT.md §5 as a shared-contract doc change (§8.7) |
| Stale text outside the cleanup's doc set | listed in `STATUS.md` §6 (README, `tests/conftest.py`, two gateway-v3 docs, `docker/README.md`, one UI heading) | one small `docs:` PR; the UI heading is a `fix(web):` PR |
| Generator default in `.env.example:8` and `docker/docker-compose.yml:17,61` | still `llm`; project default is `template` | `fix:` PR setting both to `template` (config change, call it out) |
| Gateway v3 sign-off sheet | rows 1-9 unticked, code merged | verification owner signs with dates or the review discloses it |
| `docs/RESEARCH_improvements.md` | on `origin/docs/satya/research-improvements`, no PR | decide whether to merge; it holds the E1-E3 experiment designs used below |

## 2. NEXT (in this order)

"Risk" is the risk to the prime directive (`memory_write ⟹ verdict == PASS`) and to
statistics correctness. Anything marked owner needs the verification owner's approval
(AGENTS.md §8.10).

### 2.1 Segment growth, concentration rising, forecast beats baseline as tested claims
- Why: the Exact tier reports them as figures; the plan (`docs/PLAN_data_analyst.md` §8)
  wants the inferential version checked. Today the gateway mostly tests pairwise
  associations, which a reviewer finds the least useful part.
- Effort: [estimate] 4-6 h each, including vetted templates, null schemes, attack
  applicability and tests (the plan's 2 h in §10 covered the Exact comparison and its
  claim together; the comparison is already built).
- Files: `src/pramana/contracts/enums.py` (new `ClaimType` values), `verification/admissibility.py`,
  `verification/falsification/templates.py`, `verification/schemes.py`,
  `verification/attacks/runner.py`, `analysis/planner/`, `configs/verification.yaml`, tests.
- Risk: **high, owner.** New claim types, new tests and new nulls change p-values. Needs
  known-answer tests (planted null high p, planted effect low p) and a report-card row
  per new type before the planner may propose them. Contract change (§8.7).

### 2.2 Forecast headline in the Report
- Why: the Measured forecast exists but sits under the planner's analyses at the bottom
  of the results page; it is the first thing a finance reader asks for.
- Effort: 1-2 h (plan §10; research note 3A item 3).
- Files: `analysis/computed/story.py`, `analysis/computed/summary.py`,
  `web/src/components/Computed.tsx` or `Measured.tsx`.
- Risk: none (Measured never reaches the gate or memory). Label it Measured, with the
  interval and whether it beats seasonal-naive.

### 2.3 Gate-vs-no-gate planted-truth figure
- Why: the thesis headline. No figure today shows what the gate removes and what it costs.
- Effort: about 6 h for the three experiments together (research note 3A item 1); E1
  alone [estimate] 2-3 h.
- Files: new `scripts/calibration/eval_gate_ablation.py`; reuses
  `src/pramana/evaluation/planted.py`, `metrics.py`, `verification/fdr.py`.
- Risk: none to the invariant (reads proofs, writes no memory). Write the metric, seeds
  and the "bad result" line into a committed file before the first run. Quoted numbers
  need owner sign-off.

### 2.4 BH on correlated claims: calibration
- Why: claims in one run share columns; BH's guarantee needs independence or PRDS. The
  report card uses families of one, so this is unmeasured (design W3).
- Effort: [estimate] 3 h for E2 (research note §4) run outside the sandbox.
- Files: new `scripts/calibration/eval_correlated_fdr.py`; results into `docs/`.
- Risk: the measurement is none. If FDP exceeds alpha, the fix (BY or Westfall-Young
  max-T, S10) is **high, owner**: it changes FDR (`verification/fdr.py`, `gateway.py`).
  Report the result either way; never change alpha to make it pass.

### 2.5 Second real dataset
- Why: real-data evidence is NHANES (unweighted) and UCI Online Retail II only.
- Effort: [estimate] 3-4 h to choose an open table (not famous, not MIMIC-IV), build it
  locally, run the Report and a gateway run, record results.
- Files: a build script under `scripts/`, results in `docs/evidence/`. Raw data stays in
  the gitignored `data/`.
- Risk: none. Check the licence (AGENTS.md §6).

### 2.6 Drill-down round
- Why: an analyst looks again at what stood out (plan §7 round 2).
- Effort: [estimate] 4-6 h.
- Files: `analysis/planner/` (second call, closed menu, filter from the table's own
  levels), `orchestration/analysis_integration.py`, `configs/analysis.yaml` (round cap).
- Risk: low if drill-downs stay Exact/Measured. A drill-down that proposes a tested claim
  must use exploration rows only and join the same BH family; that part is **owner**.

### 2.7 Hierarchical / DBSCAN clustering
- Why: a second view to check that KMeans segments are stable across methods.
- Effort: 1.5 h (plan §12).
- Files: `analysis/measured/segments.py`, `configs/analysis.yaml`, tests.
- Risk: none (Measured).

### 2.8 Outlier wording
- Why: plan A7: "26 against a usual 4,000", grouped by cause, reads better than a ratio.
- Effort: [estimate] 1 h.
- Files: `analysis/computed/runner.py` (`_row_outliers`, `outliers`), `computed/story.py`.
- Risk: none (Exact).

### 2.9 Partial last period
- Why: a table ending mid-month makes a false drop the headline; not detected today.
- Effort: 1.5 h (research note 3A item 2).
- Files: `analysis/computed/runner.py` (`period_change`, `data_quality`), a known-answer
  test in `tests/unit/analysis/`.
- Risk: none for Exact. If the same flag should shorten the gate's series, that is **owner**.

### 2.10 Trend method for tables over 3,000 rows (owner decision)
- Why: above 3,000 rows every trend claim is dropped, though the gate tests Kendall
  tau-b and block-differenced trends run on period means. The ceiling is the Theil-Sen
  slope's O(n²) memory (`verification/stats/effect_size.py`, `MAX_SENS_SLOPE_OBSERVATIONS`),
  checked against the full table in `orchestration/analysis_integration.py`
  (`drop_oversize_trends`) and in `chat/service.py`.
- Options: check the size of the series the test actually uses; compute the reported
  slope on a seeded subsample of pairs; or drop the slope above the ceiling.
- Effort: [estimate] 2-4 h once decided.
- Risk: **medium, owner.** Must not subsample rows silently; the permutation cost at
  large n against the 60 s timeout is a separate limit.

## 3. LATER

- Finish the A-D ablation: build conditions B and C fairly (C must be built to win),
  then run on planted tables (`PROJECT.md` §6). [estimate] 10-14 h.
- Memory ablation: do PASS lessons offered as hints improve later proposals?
- Blind planted-fact recall with decoy tables (E3), replacing the author-built 7 of 7.
- Attacks for period-change and seasonality claims (all seven do not apply today).
- Block-bootstrap interval for trend claims (S5 has none for block-differenced series).
- Online FDR for chat (S9, parked); Westfall-Young max-T (S10).
- Measured-tier false-lift rate on null targets; KNN head-to-head.
- Run-to-run variability of the planner (same table, N runs, claim overlap).
- Per-stage runtime breakdown (permutations vs interval vs attacks).
- Per-user verified memory (shared across accounts today).
- Docker run of the v3 stack, including the sandbox memory limit in the image.
- Web unit tests; keyboard, 800 px, grayscale and phone-width passes.
- Remove student registration numbers from tracked files (`git grep -l "CB.AI.U4AID"`).

## 4. Rules for any agent starting a session

1. Read `../STATUS.md`, this file, then `../AGENTS.md`. `../PROJECT.md` §5 is the contract summary.
2. Prime directive: never create a path where an unverified claim reaches the user as a
   finding or reaches memory. `memory_write ⟹ verdict == PASS`. If a change would weaken
   it, stop and say so.
3. Owner sign-off areas (AGENTS.md §8.10): p-values, FDR correction, the split, the
   sandbox and its import whitelist, the memory guard, gate thresholds and model roles.
   Build behind tests and ask; do not merge without the verification owner.
4. Models propose from closed menus; code computes and decides. DeepSeek only, traced in
   Langfuse, fail closed. No silent fallback from `llm` to `template` or back.
5. Thresholds, seeds and limits live in `configs/`; never inline.
6. Branch and PR rules (AGENTS.md §8): one task, one branch named
   `<type>/<owner>/<short-task>` from `origin/main`; small Conventional Commits; run the
   targeted tests and the full suite before committing; every change merges through a PR
   with a full description; never push to `main`; never merge your own PR without review.
7. Never commit data, `.env`, keys, local databases or personal details. Stage explicit
   paths, never `git add -A`.
8. Do not renumber sections of `AGENTS.md`, `PROJECT.md` (§1-§8) or `SCOPE.md` (§2-§7):
   code cites them.
9. Thesis report prose is written by humans (AGENTS.md §7); give outlines, not chapters.

## 5. Proposed AGENTS.md changes (owner approval needed)

Not applied. Each keeps every existing section number.

| Where | Today | Proposal | Why |
|---|---|---|---|
| Header (line 4) | "Read `PROJECT.md` first ... `SCOPE.md` for the current work scope" | add `STATUS.md`, `docs/ROADMAP.md` and `CLAUDE.md` to the read order | they now hold current state and next work |
| §1.3 | "Other modules belong to other team members" | "Stay inside `SCOPE.md`; anyone may take any item; owner sign-off areas are in §8.10" | per-person modules were dropped on 22 Oct (PR #27) |
| §2 | no bullet for the planner engine or the refuter | add: planner (DeepSeek reads Exact/Measured results on exploration rows only, returns a structured plan validated by code); refuter (S8, off by default, may only add A3 controls / A4 subgroup columns, validated by code) | both are model roles in the code with no rule text |
| §2 | Measured tier not mentioned | add: Measured models are a closed scikit-learn menu run by trusted code, never a generative model and never evidence for the gate | makes clear sklearn there is not a §4 sandbox change |
| §4 first bullet | "sandboxed/subprocess environment ... (via Celery worker)" | "subprocess sandbox in-process by default; a Celery worker is optional" | `python -m pramana` runs verification in-process |
| §8.7 | lists `OWNERSHIP.md` | "`src/pramana/*/OWNERSHIP.md`" | the root `OWNERSHIP.md` no longer exists |
| §8.10 | "The relevant module owner reviews code in their directory" | keep the safety-critical exception; drop per-directory ownership or point to `OWNERSHIP.md` files | matches one-team working since PR #27 |
| §3 (new item at the end of the list, e.g. 3.7) | none | "Any new claim type ships with a vetted template, a null scheme, known-answer tests and a report-card row before a proposer may emit it" | protects 2.1 above |
