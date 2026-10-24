# Rohith: structured local LLM claim generation

**Historical implementation record.** On 21 October 2026 the user requested
DeepSeek-only inference. The Ollama path described below has been removed.
Use [DEEPSEEK_ONLY_TODO.md](../team/DEEPSEEK_ONLY_TODO.md) and the root README for current
setup. Both hosted roles now use the shared run-traced transport; hosted analysis
does not inherit the old local-only Langfuse exception. Its bounded summary prompt
is traced (no raw rows), with exact response auditing under the run ID.

Requested by Rohith on 19 October 2026. Implements D2/W6 in the LLM decision record.
This branch starts from origin/main after candidate-selection PR #13. It does not
depend on unmerged Gemma schema-inference PR #15 or memory/API PR #18.

## Hardware decision

Observed on Rohith's Mi NoteBook Pro: i5-11300H, four physical/eight logical CPU
cores, approximately 16 GB RAM (about 6 GB free during inspection), Intel Iris Xe
integrated graphics. Ollama already has gemma2:2b (1.6 GB Q4_0) and qwen2.5:7b
(4.7 GB). Use the existing smaller Gemma model as the initial CPU profile; memory
availability makes the larger installed model a less comfortable starting point.
This is a hardware-based choice, not a measured throughput or quality claim.

Settings in configs/analysis.yaml: four threads, 4,096 context tokens, at most
1,024 output tokens, six claims, 16 schema columns, temperature zero, seed 20260817,
240-second transport timeout, one model request per run. keep_alive=0 releases the
loaded model after the request. No model download or new dependency was introduced.

## Behavior and boundaries

- `hypotheses.proposer.engine: deterministic` preserves the explicit offline
  baseline. Set PRAMANA_ANALYSIS_ENGINE=ollama to choose the local model. Missing
  tracing, transport errors or invalid responses never fall back to scan candidates.
- The prompt contains bounded univariate summaries, column roles, optional user
  question and historical hints. No participant rows, identifiers, pairwise
  association matrix, test results or deterministic candidate list are sent.
- The model returns only claim_type, two variables, direction and reference_group.
  JSON-schema output and strict Pydantic validation reject prose, p/q-values, code,
  model-authored evidence or verdicts. Unknown/unsent columns and unusable roles
  cannot become candidates. Group references must match real eligible levels.
- Code renders hedged claims and optional exploratory statistics only for the
  selected pairs. No effect threshold or observed sign silently corrects the
  model's hypothesis; the real gateway must catch wrong directions and nulls.
- Explicit `trace_backend: local` records requests under the run UUID without
  contacting Langfuse. Rohith relayed Satya's authorization for this local mode on
  19 October 2026; the exception is recorded in AGENTS.md section 2. Selecting
  `langfuse` still requires successful authentication and a run-linked generation
  before inference, with no fallback. Langfuse receives a prompt hash, not the
  local input summary/question.
- Local audits under data/runs/<run_id>/analysis_proposer.json record settings,
  prompt and exact model response. An audit is written before inference starts;
  a failed audit write prevents the request. Successful identical retries replay this
  response, rather than generating another family. A file reservation prevents
  overlapping attempts. Changed inputs/settings or recorded failures require a
  fresh run UUID; there is no automatic second model request or silent repair.
- All returned candidates remain unverified until the existing gateway executes
  its tests and applies one BH correction across the whole batch. No gateway,
  statistics library, proof schema, memory guard or sandbox code was changed.

## Activate the real model

No Langfuse credentials or .env are needed for the configured local audit mode.
Use the installed Ollama service and these commands:

```powershell
.venv/Scripts/python.exe scripts/check_llm_proposer.py --trace-backend local --preflight-only
.venv/Scripts/python.exe scripts/check_llm_proposer.py --trace-backend local
.venv/Scripts/python.exe scripts/check_llm_proposer.py --trace-backend local --verify
```

The script optionally loads .env without overriding an existing environment. It
checks the installed Gemma family before inference, uses synthetic
data, writes an ignored report, and optionally sends the one returned batch to the
actual configured gateway. It prints no keys or unverified finding sentences.
`--verify` honors the actual gateway generator selection; it does not silently
change DeepSeek to templates. With current explicit template config it is offline
verification, and no DeepSeek account is required for that check.

If the team later chooses `--trace-backend langfuse`, configure LANGFUSE_HOST,
LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in the ignored .env. This mode still
refuses missing/invalid credentials before inference; it does not switch to local.

For production entrypoints, export the same environment or load .env explicitly
(for Uvicorn use --env-file .env). Setting an engine only in the check script does
not change the parent shell environment or silently modify project configuration.
Direct calls accept run_id, user_query and lesson_hints. Native graph calls pass
run_id and user_query, and keep the existing exact cleaned-data reference.
Automatic memory retrieval/injection is a separate integration task; accepting
explicit hints here does not claim automatic episode mode is complete.

## Review and integration

Rohith's scope now records his authorization for D2/W6. The shared-client W4 remains
B. Karthikeya's work; this bounded analysis-only Ollama adapter can be moved behind
that interface when available. No common client or verification model was replaced.

The only orchestration change adds existing run_id/user_query values to the existing
analysis function call. It changes no graph nodes, shared payload model or queue
behavior. B. Karthikeya should review that adapter change before merge. PROJECT.md
and the analysis config changes also need the affected owners' review. Default
offline tests remain deterministic; live LLM activation must be called out separately.

Official references: [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs),
[installed Gemma tag](https://ollama.com/library/gemma2:2b),
[Langfuse project keys](https://langfuse.com/faq/all/where-are-langfuse-api-keys).

Validation on 19 October 2026: 144 analysis tests passed; 148 combined targeted
analysis/adapter/handler tests passed; the new real-gateway integration test passed.
Full suite: 540 passed, five existing enum collection warnings, 182.63 seconds.
Repository lint, analysis/adapter/script mypy and diff checks passed. The initial
Langfuse preflight refused missing credentials. After Satya's local-mode approval,
an actual CPU run of gemma2:2b completed with 913 prompt tokens and 211 output tokens
in 37.60 seconds of Ollama-reported total duration (cold model run). It produced
six structured proposals: one passed structural validation and five were rejected
for incompatible roles. The surviving age/bmi association on synthetic data was
tested by the real gateway and received PASS (p=q=0.00009999000099990002). No memory
write was performed by the check. This single synthetic smoke test establishes
working local inference/validation/verification, not broad proposal quality or
benchmark precision. Full local artifacts remain ignored under data/runs/ and artifacts/.

After the explicit local/Langfuse backend update: 146 targeted analysis/gateway
tests passed; full suite 541 passed with five existing enum collection warnings
in 187.45 seconds. Lint, mypy and diff checks passed again.
