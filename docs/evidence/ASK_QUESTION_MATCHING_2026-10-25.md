# Ask: everyday column names and compound questions

## What failed

The question "Does this dataset prove that age causes systolic blood pressure to
increase, and is it representative of the general population?" was refused as
unrelated to `age_years` and `systolic_bp`. Exact identifier matching missed ordinary
names, and the reply omitted the causation and representativeness questions.

## Changes

- Chat resolves whole identifiers, spaced names, optional known unit suffixes,
  complete codebook labels and recognised sector-role phrases. Explicit synonyms
  include systolic blood pressure/SBP, diastolic blood pressure/DBP, blood sugar and
  body mass index. It does not use arbitrary single words from a label as matches.
- More specific overlapping phrases win. Ambiguous meanings require clarification
  before any model or test call; the model cannot resolve ambiguity by inspecting
  its preferred column. Unrelated proposals remain blocked.
- Resolved references are included as data in the model input. The prompt directs
  mixed association/causation/population questions to test the association.
- Code explains the limits of causation and population representativeness even if
  model wording fails its checks. Population claims cannot be established by cited
  descriptive counts. A reply testing only part of a multi-column question says
  which other referenced columns were not tested.
- Chat PASS explanations now accurately describe a single test, rather than implying
  correction across multiple chat questions. The disclosure still reports earlier
  tests, and q equals p for the family of one.

No statistics, threshold, FDR, sandbox, proof contract or memory policy changed. Chat
still never writes to memory. Older failed tests remain historical failed attempts;
resubmit the question to test it with the new code.

## Repeated live checks

Two isolated runs used only the generated synthetic fixture
`tests.fixtures.sample_data.sample_frame()` (500 rows, fixed seed). They did not read
the user's uploaded file. Upload-sector/summary calls were explicitly offline for
this diagnostic; chat and falsification-code generation used real DeepSeek calls
with Langfuse enabled, and the real sandbox/gateway executed the generated tests.

| Scenario | First run | Final-code repeat |
|---|---|---|
| Original compound question, asked twice per run | Both association tests PASS; both limitations explained | Same |
| AGE / SBP paraphrase | PASS | PASS |
| Age / independent noise | REJECT | REJECT |
| Dataset meaning | Tentative health interpretation followed by facts | Same |
| Population-only question | Unknown sampling/representativeness explained | Same |
| Blood pressure with both systolic/diastolic present | Clarification; zero model calls/tests | Same |
| Meaning of x/y dataset | Subject explicitly unknown | Same |

All sixteen scenario checks passed, including persisted-answer/history agreement.
Each run recorded exactly four claim tests and initialised no memory database.
The first run exposed the misleading multiple-test explanation; the final repeat
checks its corrected wording explicitly.

Ignored receipts:

- `data/acceptance/ask-paraphrases-21425bf4-713b-40df-8680-422057b9e56a/receipt.json`
- `data/acceptance/ask-paraphrases-2b04b3b6-82db-4162-9f4d-e4f4c23d4c8c/receipt.json`
- `artifacts/ask_paraphrases_live.log`, `artifacts/ask_paraphrases_live_final.log`

## Automated checks

Final targeted chat/API checks: **102 passed**, two existing warnings
(`artifacts/ask_language_targeted.log`). Ruff passes and source mypy passes across
174 files. The complete suite passed in two disjoint partitions: **1,347 passed**,
23 existing warnings. Independent collection confirms exactly 1,347 tests
(`artifacts/ask_language_collection.log`).

| Partition | Result | Time | Ignored log |
|---|---|---|---|
| All tests outside `tests/unit/verification` | 881 passed, 20 warnings | 606.55 s | `artifacts/ask_language_suite_application_final.log` |
| `tests/unit/verification` | 466 passed, 3 warnings | 614.61 s | `artifacts/ask_language_suite_verification.log` |

An earlier application pass was stopped and restarted after the final wording
corrections; its partial log is not counted. Existing warnings include pytest enum
collection, the pre-existing helper returning a dictionary and dependency deprecations.
`git diff --check` passes. No application source changed after the final application
partition began; the earlier verification partition covers unchanged verification code.

Independent audit: all eight saved DeepSeek-written programs executed again in the
sandbox and exactly reproduced raw p, effect, metric and reported-effect fields.
Independent SciPy Spearman calculations matched every effect within 1e-12. Each
stored q equalled p, as required for chat's family of one. Across both sessions:

- Age/pressure: rho 0.9628842355369421, p = q = 0.00009999000099990002; six PASS tests.
- Age/noise: rho 0.01547439789759159, p = q = 0.7314268573142686; two REJECT tests.
- Remote Langfuse metadata: fourteen message traces, 44 model requests, 61,968 input
  tokens and 4,191 output tokens, all `deepseek-flash`; monetary cost unavailable.
- The ambiguous question used zero model requests in each session.

`artifacts/ask_language_audit.json` and `.log` retain this audit. Replaying and
reading trace metadata made no inference calls and wrote no memory records.

The updated preview is served on port 8087 with the existing accounts and uploads
preserved. `/health` returns HTTP 200. No browser visual/accessibility acceptance is
claimed, and no changes have been committed or pushed for this follow-up.

This is focused acceptance evidence, not a guarantee for every natural-language
question. Unrecognised synonyms, ambiguous wording, unsupported tool requests and
questions exceeding the single-test budget can still require clarification or refusal.
