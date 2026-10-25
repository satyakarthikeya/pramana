# Ask reliability branch validation — 25 October 2026

This is the scoped Git delivery of the Ask reliability work. Base: `origin/main`
at `f0c00ba` (PR #37). Branch: `fix/b-karthikeya/ask-reliability`.

The original checkout contains additional uncommitted report, analysis, gateway,
typing, dependency and release-readiness work. This branch was built in an isolated
checkout so those changes are not silently staged. Only chat interpretation and
presentation, overview/totals tools, their regressions, the matching Ask UI changes,
and historical acceptance evidence are included. Target-specific pair scanning,
AnalystBrief, shared configuration and dependency upgrades are excluded.

The four companion acceptance documents describe earlier broader working-tree
checks and live synthetic sessions; their test counts are historical, not claims
about this extracted branch. The synthetic CSVs, stores, screenshots, credentials,
browser state and local audit scripts remain ignored and are not in this PR.

The Ask change depends on a separate test-isolation fix on
`fix/b-karthikeya/test-reliability`. Its executor change restores `_run_once`
after the E1 module fixture finishes, including failure paths. Main's ablation
plumbing test had left an in-process shim installed, so the later executor timeout
test executed its infinite loop in the pytest process. The stalled full run was
stopped; it is not counted as passing. Production executor code, statistical logic
and experiment behavior are unchanged. The verification owner must review the
test-reliability PR before merge; no approval is asserted here.

The application partition then exposed the existing Measured budget test's sleep
occurring before the function starts its timer. A second test-only commit replaces
that sleep with a controlled clock scoped through pytest monkeypatch. Measured
runtime/models are unchanged. The remaining edits and model-family test in the
original checkout's `test_measured.py` remain excluded. Analysis-owner review is
also needed for this small test-reliability dependency.

The latest main's `render_outcome` function and its verification-config import are
preserved verbatim, including the verification owner's repeated-chat-testing
disclosure. Initial extraction caught a failed `test_luck_note` because copying the
older engine lost that new function body; it was restored, and the incomplete
pre-integration full run was stopped. Neither attempt counts as final validation.

## Scope and contracts

- Column matching is lexical: common naming conventions, known units and full
  aliases; ambiguous meanings require clarification. No conversion or statistical
  choice is added.
- Future requests receive an explicit capability response; recorded forecast-error
  metrics remain describable. Missing/unanswered association requests cannot be
  disguised as an answered schema overview.
- Descriptive `overview` and numeric sums are code-computed; guarded fallback prose
  uses only recognised tool fields. Cleaning scope is shown and persisted.
- `ChatAnswer.wording_source` is optional for legacy messages. The UI labels computed
  summaries, exposes their evidence and preserves line breaks.
- No verification contract, threshold, split, test mathematics, sandbox or memory
  policy changes. Chat still writes no lessons; memory requires PASS.
- Chat, workspace-tool and frontend owners should review before merge. No review
  or verification-owner approval is asserted by this document.

## Checks on this extracted branch

- The branch independently collects 1,453 tests, including main's newer forecast
  and calibration coverage.
- The locked frontend dependency install and production TypeScript/Vite build pass.
  No manifest or lockfile is modified. The inherited main lockfile reports one high
  and one moderate npm audit advisory; the separate local Vite upgrade is excluded.
- Ruff on changed Python modules/tests and `git diff --check` pass.
- The ablation module followed by the real timeout regression passes all five
  tests in 8.67 seconds after fixture restoration; this order previously hung.
- Targeted chat suite: 120 passed, one existing warning.
- Application partition: 920 passed, one failure in the old budget test, twenty
  existing warnings, 1,067.22 s. Its 887 non-Measured cases passed unchanged.
- Complete Measured module after the controlled-clock correction: 34 passed,
  71.82 s. This replaces its earlier 33 passes and the one failed budget test.
- Complete verification partition after executor-fixture restoration: 532 passed,
  three existing warnings, 1,271.58 s.
- Together these provide passing coverage for all **1,453 distinct cases**:
  887 other application cases + 34 freshly rerun Measured cases + 532 verification
  cases. The earlier failures and stalled runs are not relabelled as passes.

No production Python change followed the final partition runs' start. Only the
budget test was corrected after its application failure; its entire module was
then rerun. The dependency PR contains the two test-only fixes in small commits;
the Ask branch adds its twenty scoped files on top. Merge the dependency first,
then update the Ask branch before merging it. Neither PR is self-merged.

Local-only receipts: `artifacts/ask_push_full_suite_final.log` and the isolated
checkout under `artifacts/ask-reliability-push/` in the original workspace. Final
partition receipts are `artifacts/ask_push_application_final.log`,
`artifacts/ask_push_measured_final.log`, and `artifacts/ask_push_verification_final.log`.
They are
not committed or packaged as product data.
