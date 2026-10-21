# DeepSeek live acceptance — 21 October 2026

Engineering evidence, not capstone report prose or independent release approval.
Branch: `feat/b-karthikeya/deepseek-only`, based on integrated main `a5ed8e3`.
The user entered credentials locally and explicitly resumed testing. Credentials
were not printed, copied into frontend assets, committed or changed by these tests.

## Results

| Check | Observed result |
|---|---|
| Credential/configuration preflight | All required fields present; explicit API/LLM profile and Langfuse enabled |
| Live proposal + falsification smoke | 3 eligible claims; **1 PASS, 2 REJECT**; actual code/statistics, no template fallback |
| Website synthetic sample | 6 claims; **1 PASS, 5 REJECT**; planted age/BP pair passes; pilot decoy rejected |
| Related second website upload | 6 claims; **1 PASS, 5 REJECT**; historical hint received and fresh verification performed |
| Group/trend upload after prompt clarification | **1 PASS, 1 REJECT**; trend supported; wrong signed group claim refuted |
| Persisted memory | Exact set of each audited run's PASS IDs; no REJECT lessons present |
| Website interactions | Preview/progress, readable/raw proof, real JSON/CSV downloads, memory browse/search, keyboard focus and 1366/390px layout checks passed; zero JS exceptions |
| Reproducibility | All **14** programs from the two website runs and group/trend run re-executed from stored source; raw p/effects/metric values identical |
| BH audit | Family sizes **6, 6, 2**; one family ID per run; recomputed q-values exactly match stored proofs; no new hypothesis family submitted |
| Remote observability | Langfuse observations API v2 returned each run's DeepSeek generations, actual usage and matching trace IDs |
| Invalid credential | One intentionally invalid dummy provider key refused without retry/provider fallback; no production key changed and no memory write path invoked |

The browser check used installed headless Chrome, not a human-controlled Windows
session or second machine. The computer-use skill's required runtime was unavailable;
the existing DevTools acceptance harness was used and its screenshots inspected.
The embedding model was the genuine previously cached MiniLM model, copied unchanged
to the fresh test-store cache; this was **not** a cold-install acceptance test.

## Run identifiers and proof examples

- Smoke: `989a7548-c9ea-497f-86e0-a695e01d9ae2`.
  Strong age/BMI claim: p `0.00009999000099990002`, q `0.00029997000299970003`,
  rho `0.9660740329189526`; the other two eligible correlations were inconclusive.
- Browser sample: `5e2b5ea8-b6b9-41b7-9d04-7f12af0d4df1`; journey **90.204 s**.
- Browser related upload: `6a6a546d-4107-4ef2-bc62-40fdc8e1aefb`; journey **81.133 s**.
  Both age/BP proofs: rho `0.9628842355369421`, p `0.00009999000099990002`,
  q `0.0005999400059994001`. The second table adds two BP units to the first;
  an identical rank correlation is expected, not evidence of cached verification.
  Replayed sources and distinct run traces establish fresh execution.
- Group/trend: `45efd703-9b3b-44e7-ba0b-1b30b338a2a1`.
  True trend: tau-b `0.5500190982169267`, p = q `0.00009999000099990002`, PASS.
  The model claimed the measure was higher in rural than urban. The recipe has
  higher urban values; execution found delta `-0.8333333333333334`, p = q
  `0.00009999000099990002`, and **REJECT / REFUTED**. A small p did not override
  the direction check. The trend alone was admitted to memory.
- Invalid-key transport check: `595752df-cfca-4234-b541-123c27de39a6`.

## Issues and limitations recorded honestly

1. The initial smoke proposed three two-group claims with null direction. The
   validator rejected those before verification; it did not guess a direction.
   The prompt's generic nullable-direction sentence was ambiguous. It now states
   that two-group direction MUST be positive/negative or the claim must be omitted;
   null remains allowed for correlation/trend and required for multi-group claims.
   The regression assertion and subsequent live mixed-type run exercise this fix.
   No accepted batch was regenerated, revised or resubmitted to force significance.
2. Extra shuffled-column coverage run `ac1dad97-7d6e-408b-9f0b-f0fac8393d91` completed
   with one true-pair PASS, but the model **did not propose the shuffled decoy**.
   `check_v1_truth.py` therefore failed its expected-decoy assertion. This is an
   unmet coverage condition, not evidence that the decoy was rejected or a gateway
   false PASS. The completed family was not retried. Both main website runs did
   propose and reject the pilot decoy; no test assertion was relaxed to hide this.
3. The first Langfuse read attempted the old SDK trace endpoint and received HTTP
   410 (`LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`). Readback was moved to bounded
   `/api/public/v2/observations` queries, which returned HTTP 200 and the real spans.
   Product inference was already using the SDK's observation/OTEL path, not the
   legacy trace-read endpoint. See [the official API guide](https://langfuse.com/docs/api-and-data-platform/features/public-api).
4. Langfuse/model metadata had actual token usage but no resolved token prices or
   cost. Cost is **unknown**, not zero. Audited API runs recorded respectively
   7, 7 and 3 model requests. Their input/output counts were 6768/2208,
   6811/2206 and 3259/932. Outer analysis validation observations are not additional
   provider requests and were not double-counted.
5. Missing tracing, malformed/truncated outputs, provider failures and unsafe
   generated code are covered by automated fail-closed fixtures. Apart from the
   invalid-key transport check, these are **not** claims of live fault injection
   against the running website or a production chaos test.

## Reproduction and artifacts

Final post-fix offline suite: **781 passed, 14 warnings in 533.45 s**.
Whole-repository Ruff, targeted mypy (seven runtime files plus the new audit script),
`pip check`, dashboard `node --check` and `git diff --check` passed. The warnings
are the existing TestType collection and test-only Chroma embedding notices.

The live app is running on `http://127.0.0.1:8081`. This instance uses ignored
`data/deepseek-acceptance` and real persistent Chroma/MiniLM, with `.env` credentials.
Do not start a second app on that port or accidentally test an older container.

Commands used:

```powershell
.venv\Scripts\python.exe scripts/check_llm_proposer.py --preflight-only
.venv\Scripts\python.exe scripts/check_llm_proposer.py --verify
node scripts/check_v1_browser.mjs
.venv\Scripts\python.exe scripts/check_v1_truth.py --url http://127.0.0.1:8081
.venv\Scripts\python.exe scripts/check_deepseek_live.py `
  --run-id 5e2b5ea8-b6b9-41b7-9d04-7f12af0d4df1 `
  --run-id 6a6a546d-4107-4ef2-bc62-40fdc8e1aefb --mixed
```

The truth command has the coverage failure described above, not a passing result.
`--mixed` starts **one new paid run**. To repeat only the stored-source/trace audit
without more inference, replace `--mixed` with
`--run-id 45efd703-9b3b-44e7-ba0b-1b30b338a2a1`. Only audit known local acceptance
runs; this script requires executed proofs and deliberately fails on missing data,
failed source replay, incomplete traces or unexpected memory contents.

Ignored evidence:

- `artifacts/llm_proposer_989a7548-c9ea-497f-86e0-a695e01d9ae2.json`;
- `artifacts/v1-browser/acceptance.json`, downloaded result JSON/CSV and four PNGs;
- `artifacts/deepseek_live_acceptance.json` (model usage, proof metrics, source hashes,
  remote trace readback and exact replay results; no API keys);
- exact cleaned frames and proposer audits under `data/deepseek-acceptance/runs/`.

Current release limitations: affected-owner review/PR checks, independent human
rehearsal, clean clone/second machine, broad model-quality/benchmark evaluation,
cloud acceptance and human report/freeze gates are still pending. These synthetic
successes do not establish universal model accuracy or whole-project completion.
