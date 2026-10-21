# V1 implementation and acceptance log — 20 October 2026

This is engineering evidence, not capstone report prose. Work is on
`feat/b-karthikeya/v1-product`, based on unmerged workflow PR #22 plus the
published V1 docs branch (PR #24) and optional hosted-Gemma branch (PR #23).
Dependency integration is not a claim that those PRs were merged or reviewed.

## Implemented and exercised

- Local `python -m pramana` entrypoint; explicit template V1 profile, in-process
  gateway, one active run, eight-candidate cap before gateway invocation.
- No verification threshold, resample count, seed, sandbox restriction, BH family
  or verdict rule changed. The standalone gateway retains its LLM default.
- Preview, stage/per-claim progress, friendly errors, configured-band strength
  words, readable and raw proof views, JSON/CSV download, generated synthetic
  sample, new-analysis control, historical hints and memory source links.
- Unit/API tests cover unreadable/empty/no-usable tables, upload limits, trend
  ceiling, missing verifier key, progress, previews, fresh two-run verification,
  PASS-only memory and safe downloadable exports.
- Full-suite rerun: **771 passed, 13 warnings in 414.62 s** (an earlier run
  also passed in 426.31 s). Python runtime code was unchanged afterwards; final
  UI-only wording/toggle ordering is covered by repeated browser acceptance.
  Warnings are enum collection
  and explicitly labelled test-embedding deprecations, not skipped tests.
- Ruff, Node syntax checks, Mypy (37 relevant Python source files) and `pip check`
  passed. No browser dependency was added: a stalled optional Playwright download
  was stopped and the declared dependency removed before commit.

## Browser method and successful evidence

Computer-use's JavaScript runtime was unavailable. The substitute is installed
Chrome in an isolated **headless** profile, driven through its local DevTools
protocol by `scripts/check_v1_browser.mjs` (Node 22+, no npm package).
This is actual browser execution, not mocked HTML or a manual Windows rehearsal.

The app runs at `http://127.0.0.1:8081`, using isolated ignored
`data/v1-acceptance/`, deterministic proposal, explicit template verification,
10,000 configured permutations and real MiniLM/Chroma storage. Docker/Redis/Celery
are not used to execute V1 runs. Already downloaded identical MiniLM weights were
copied from the local development Docker cache to avoid another slow download;
therefore this is **not a cold clean-clone setup acceptance**.

The browser performs the sample and a distinct related upload (synthetic BP
values shifted by +2), waits for complete results, validates the true pair and
decoy outcomes, opens readable/raw proofs, downloads/parses both exports, browses
and searches memory, verifies second-run historical hints, checks keyboard focus
and checks no horizontal overflow at 1366px and 390px.

Successful post-fix browser evidence is regenerated at ignored
`artifacts/v1-browser/acceptance.json`; screenshots and downloaded JSON/CSV sit in
the same directory. Earlier clean run:

| Dataset | Run ID | Result | End-to-end browser duration |
|---|---|---|---|
| Synthetic sample | `54970671-5b7e-4ac5-bf4f-ac44cbc01f38` | 1 PASS, 2 REJECT | 16.109 s |
| Related second upload | `24ef6b4a-642c-4cea-a68a-a5336c4f0fc0` | 1 PASS, 2 REJECT; source-verified hints | 16.862 s |

Both stored only PASS findings. Repeated later screenshot runs use new run UUIDs;
consult the artifact's recorded IDs rather than conflating separate executions.
No paid inference or remote Langfuse acceptance is asserted.

## Separate shuffled-decoy check (G3)

`scripts/check_v1_truth.py` uploaded a strong pair and a weak shuffled copy through
the actual API. Build seed `20261020`; source permutation selected for weak
exploratory rho before any verification, never using a p-value or verdict to tune
the dataset. This illustrates rejection; it is not an empirical-FDR experiment.

Run `b9c785e6-0e76-4e04-a899-38338da0b509` completed: true pair supported,
shuffled decoy rejected, complete proofs, only PASS stored. Exact results/programs
are in ignored `artifacts/v1_truth.json`.

## Defect and prerequisite log

| Observation | Resolution / boundary |
|---|---|
| Test clicked sample before deferred JS handlers were ready | Harness now waits for document and handler readiness |
| Restricted test process could not fetch first-use embeddings | Failure degraded safely; restart with network access, then reuse the existing identical local model cache |
| First-use model download was slow | README explicitly describes initial network/model setup; no second-machine/cold-install success claimed |
| Approximate memory query honestly had no hit at the configured cutoff | UI already showed its empty state; harness uses exact stored text for guaranteed-hit testing, without changing similarity thresholds |
| Completion page still said to wait | Terminal result now changes the message to verification complete |
| A very fast result could have its final message overwritten by acceptance copy | Acceptance copy is now set before awaiting result selection |
| Raw JSON stayed expanded for the next proof | Each new proof resets raw JSON to closed |
| Desktop screenshot kept stale scroll position after width change | Harness scrolls to the actual findings after each viewport resize |

## Reproduce

```powershell
.venv\Scripts\python.exe -m pramana --port 8081
# In another terminal, against that local app:
node scripts/check_v1_browser.mjs
.venv\Scripts\python.exe scripts/check_v1_truth.py
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
```

The browser script refuses a non-local app or occupied debugging port; its
synthetic files, profiles, screenshots and downloads remain ignored.

## Still required — do not tick without evidence

- Review and merge PRs #22/#23/#24 and the V1 product PR in dependency order,
  with affected-owner and verification-owner approvals; no self-merges.
- Run suite/lint on merged current main (G2). Feature-branch green is not main green.
- Clean-clone installation and full journey on a second machine (A5); a teammate
  must test without this machine's prepared package/model caches.
- Optional funded hosted-Gemma acceptance/cost record (C2), if the team wants it.
- Contract/whitelist notices were published in
  [PR #25's review comment](https://github.com/satyakarthikeya/pramana/pull/25#issuecomment-6288098957).
  Affected-owner acknowledgments remain required; no private notifications or
  individual approval is implied by publishing a repository review notice.
- Human-written report (G6), human rehearsal/sign-off and the scheduled 26 October
  freeze. No agent-authored capstone report or premature code-freeze claim.
- Team decision on deleting historical docs after review; no material files removed.
