# Ask tab: readable dataset introductions — 25 October 2026

## Problem and fix

The saved question "what is this data about" had valid `missingness` and `describe`
tool results, but its model wording failed the number guard. The response displayed
two diagnostic paragraphs and left the actual results collapsed. This was not a
gateway failure: no claim was submitted for verification.

- Added a fixed `overview` tool: actual row/column counts, bounded column list,
  detected roles, claim eligibility and missing counts. It examines no hypotheses.
- The chat prompt directs dataset-introduction questions to this tool and prohibits
  guessing dataset origin or sampling design from names.
- Unsupported model wording is still withheld. Known descriptive tool outputs can
  now supply a bounded, code-rendered summary, labelled `wording_source: computed`.
  The numeric/verdict guards are unchanged; no additional model retries are added.
- The UI labels computed summaries, displays line breaks, opens their evidence, and
  avoids repeating the same withholding diagnostic as the main answer.
- Legacy withheld replies are rendered from their stored tool evidence when read.
  Their original database record, timestamp, usage counts and testing ledger are not
  rewritten. No model call or data change is needed to view the improved summary.

Changes are on `fix/b-karthikeya/ask-overview`, depending on the existing uncommitted
finishing/report work. No dependency or verification-contract changes. The optional
chat-owned `wording_source` field defaults to absent for older records. Workspace,
chat and frontend changes need their module owners' review before merging.

## Evidence

The actual saved exchange was checked locally, read-only. It now renders 500 rows,
the four inspected column names, 460 missing values in `moon_phase_pilot`, and the
recorded `systolic_bp` descriptive statistics. Its stored JSON was verified unchanged.

Automatic approval review rejected a proposed external test using the uploaded file
because its sensitivity was unestablished. That command did not execute. The live
test was changed to generated synthetic measurements from
`tests.fixtures.sample_data.sample_frame()` (seed 20261020); it does not access or send
the uploaded file. Local record inspection remained read-only.

Synthetic live session: `ask-overview-7864b471-52a2-4e28-8e9a-51b0fc4ab44d`.
Message trace: `41b2ffe6-c73a-4c8a-b126-246069df7ad4`.
The exact question returned a descriptive computed summary: 500 rows, four columns
after the normal cleaner removed the constant column, column names and the limit on
inferring provenance. One overview call, two DeepSeek Flash calls, 2,609 input and
106 output tokens. No claim test or verified-memory initialisation/write occurred.
History reload matched the answer. Cost is unknown, not zero.

The first immediate trace-read assertion found no remote observations because the
SDK had not finished its asynchronous export; the helper exited 1 after the chat/API
assertions succeeded. A later **metadata-only** readback confirmed both model calls
and matching usage. No new inference was run to obtain that readback. The failure and
answer are retained in ignored `artifacts/ask_overview_live.log` and the isolated
session's database. Do not present the helper's initial exit status as a full pass.

## Checks

- Targeted chat guards/engine/presentation, workspace and chat API: **118 passed**, two
  existing warnings, 60.46 s (`artifacts/ask_overview_targeted.log`).
- Ruff, source mypy (173 files), and TypeScript/Vite production build: pass.
- Full suite completed in three disjoint partitions, **1,324 passed**, 23 existing
  warnings in total. A separate full collection confirms exactly 1,324 tests:

  | Partition | Result | Time | Ignored log |
  |---|---|---|---|
  | Application/integration (all tests outside `tests/unit/verification`) | 858 passed, 20 warnings | 591.21 s | `artifacts/ask_suite_application.log` |
  | First 15 sorted verification test files | 336 passed, 2 warnings | 313.31 s | `artifacts/ask_suite_verification_a.log` |
  | Remaining 15 verification test files | 130 passed, 1 warning | 311.82 s | `artifacts/ask_suite_verification_b.log` |

  Existing warnings include imported test-type enums, dependency deprecations and
  the existing pytest helper returning a dictionary; they are not hidden as fixed.
  No application source changed after these partitions began.

The local preview was restarted on port 8087 with the existing account/upload store
preserved. Refresh the Ask tab to see saved replies rendered with the new code. No
visual/browser-accessibility pass or comprehensive chat-quality benchmark is claimed.
Health returns HTTP 200. Nothing was staged, committed or pushed for this fix.

## Follow-up: answer the subject question first

The first fix still led with dimensions, which did not answer what the dataset was
about. Dataset-introduction questions now lead with a tentative subject explanation
using the existing deterministic sector vocabulary and recognised column roles. For
the saved example, age and systolic blood pressure suggest a health-related dataset.
This is explicitly an interpretation of names, not confirmed provenance, row identity,
study purpose, or evidence that the records are real. Weak or tied vocabulary matches
produce an explicit inability to identify the subject and request a description or
codebook. Dimensions and computed summaries follow the explanation.

Even a numerically valid but count-only model answer gets this introduction. Other
calculation questions keep their existing behavior. Previously saved descriptive
introductions get the same read-time rendering; no records are rewritten and no model
call is needed. The gateway, statistics, memory and wording guards are unchanged.

Follow-up checks: 83 chat/API tests passed (two existing warnings); after the final
wording polish, all 45 engine/presentation tests passed again. Chat Ruff and mypy pass,
as does `git diff --check`. The earlier 1,324-test full-suite result above predates this
follow-up; no new full-suite result is claimed. No additional hosted inference was
needed. The original saved exchange was checked locally, and the preview restarted
on port 8087 with the same accounts, uploads and history.
