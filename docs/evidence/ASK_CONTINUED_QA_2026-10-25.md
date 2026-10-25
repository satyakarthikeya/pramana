# Continued Ask acceptance — 25 October 2026

This resumes the saved cross-domain follow-up, whose final evidence already records
19 browser scenarios and 1,359 passing tests. Those earlier counts are historical;
the new cases below use fresh synthetic energy and education CSVs, with 120 unique
records each and seed 20261025. This is finite engineering acceptance, not a claim
that every dataset or natural-language question works.

## General parsing fixes

- Conventional unit symbols and their lowercase header spellings share lexical
  aliases. This covers split camelCase symbols such as kWh, kW, mA, MPa and kPa,
  ordinary electrical names such as voltageV/currentA, and spelled-out qualifiers.
  Ambiguous units still require clarification. No value is converted or inferred.
- Forecast requests are recognised with future wording on either side of the
  prediction verb, a dated prediction request, or a future `will` question.
  Recorded forecast error, residual, accuracy, bias and performance metrics remain
  available to descriptive tools. This changes the capability response, not forecasting.
- When guarded model wording is withheld on an explicit association/correlation
  question and only descriptive tools ran, a table summary is now labelled
  `unanswered`. Code states that the association was not answered and no test ran.
  It does not guess a missing field's identity or repeat unchecked model explanations.

Twelve parsing cases and one fallback case failed before their fixes. Final coverage adds
24 regressions, including
the chat-loop guarantee that future requests call neither the model nor verifier,
and that a recorded forecastError column can still be described.

No statistic, threshold, split, FDR correction, sandbox, contract, dependency or
PASS-only memory policy changed. The existing task branch is retained; nothing is
staged, committed or pushed by this continuation.

## Website method and independent answers

The actual upload and Ask forms were driven through the connected in-app browser
against an isolated server on port 8089. Its account, uploads and history are under
ignored `data/acceptance/continued-qa-20261025/`; the personal preview's store was
not modified. DeepSeek and required Langfuse tracing remain enabled.

The first energy analysis failed closed because the sandbox denied outbound sockets
to Langfuse. That failed attempt remains in history. The isolated server was then
restarted with network permission. No failed analysis is counted as a successful
live workflow. Education was uploaded after the final parser changes were loaded.

Independent calculations from the original CSV bytes:

| Quantity | Reference |
|---|---:|
| Energy total, kWh | 1017.4254505790842 |
| Recorded forecast-error mean | -0.049113785787445914 |
| Voltage/current Spearman rho | 0.9786096256684491 |
| Exam-score mean | 61.79873870851123 |
| Group A exam-score mean | 63.96300567282355 |
| Group B exam-score mean | 61.37297780207225 |
| Group C exam-score mean | 60.02907941358138 |
| Study-hours/exam-score Spearman rho | 0.980686158761025 |

The energy total and forecast-error mean match the displayed six-decimal answers;
voltage/current was actually tested by the gateway. The proof drawer displayed the
saved executed Python. A numerical-injection question produced a computed summary
without the requested invented number, and that answer survived reload.

Three future questions (including reversed word order and a numeric target year)
showed the explicit no-forecast explanation and zero model calls/tool steps.
Education's overall mean and three group means match the independent reference;
the group comparison is labelled exploratory, not verified.

## Limitations observed, not hidden

- The missing-household-income question produced a safe column-summary fallback,
  with no substituted test, but did not directly explain the missing field. That
  initial answer-quality failure remains in history. The final repeat displays
  `No answer` and explicitly says no association test ran. The missing relationship
  remains unanswered; the system does not invent a substitute field.
- A compound education question initially hit the shared verifier slot while the
  analysis was downloading its embedding model. It correctly disclosed that no
  test ran and displayed both causation and population limitations. This busy
  response does not count as a completed association test.
- After the run finished, one retry of the compound question actually tested
  studyHours/examScorePct. Both limitations remain visible; the supported association's
  rho is 0.980686158761025. An independently generated attendance/study-hours pair was
  rejected: rho -0.009882630738245711, p = q = 0.9151084891510849. No repeat was made to
  obtain a preferred statistical result.
- The existing deduplication limitation from the retail acceptance report remains.
  These fresh fixtures have unique identifiers, so no rows are removed.
- Lexical aliases and future-request detection cover a finite vocabulary. Unknown
  synonyms and complicated mixed requests can still require clarification/refusal.

## Receipts and verification

Ignored evidence: `data/acceptance/continued-qa-20261025/fixtures/`, `ui-receipts.json`,
`screenshots/`, and `audit.json`. The independent replay script is
`artifacts/audit_continued_qa.py`; it reads only this synthetic test database and
fixtures, reruns saved code through the existing sandbox, and makes no inference
calls or memory writes.

Fourteen UI exchanges were persisted, including the initial limited/busy replies and
their explicit repeats. All declared numeric and safety checks passed; this does not
relabel an unanswered question as a substantive answer. All three chat programs
replayed exactly, including raw p, gating effect, reported effect and metric labels;
independent SciPy effects match within 1e-12. Each chat q equals p. The null proof
drawer's code and answer were inspected and retained after reload.

Remote Langfuse metadata readback found eleven message traces with thirty model calls,
45,117 input and 1,818 output tokens. All calls used `deepseek-flash`; cost is unknown.
The isolated memory store contains one PASS lesson from the education analysis and
zero lessons from any chat message. `trace-memory-audit.json` retains the metadata.
The audit made no inference calls. The earlier failed upload trace is not counted as
successful tracing evidence.

The first full-suite run passed 1,359 existing tests (23 existing warnings). It was
started before the new regressions and is not the final-source check. The final
source collects 1,383 tests. The final chat/API/workspace check passed 177 tests with
two existing warnings; ruff across src/tests/scripts, mypy across all 174 source files,
and `git diff --check` pass. The production
UI build passes; its first sandboxed attempt failed on parent-directory read access
and was rerun with permission.

| Check | Result | Receipt |
|---|---|---|
| Additional full-suite run, before the final fallback fix | 1,382 passed, 23 warnings; 1,232.30 s | `artifacts/continued_qa_suite.log` |
| Final application partition, after the last source change | 917 passed, 20 warnings; 654.05 s | `artifacts/continued_qa_application_final.log` |
| Final targeted chat/API/workspace pass | 177 passed, 2 warnings; 101.63 s | `artifacts/continued_qa_targeted_final.log` |

The full pass includes all 466 verification tests, whose source and configuration
were unchanged throughout this continuation. Together those 466 and the final 917
application tests cover the independently collected final tree: **1,383 passed**, with
23 existing warnings across the disjoint partitions. No application source change
followed the final application partition's start. Intermediate/initial replies and
failed checks remain in their receipts and are not relabelled as successful answers.

The isolated final-code website remains running on port 8089, with its synthetic
account and data preserved. This continuation did not restart or modify the personal
preview's process/store on port 8087; that process needs its usual restart to import
the updated Python source. No credentials are stored in this document.
