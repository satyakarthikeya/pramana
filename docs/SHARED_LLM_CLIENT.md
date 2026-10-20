# Shared inference client (W4)

Owner: B. Karthikeya. Additive public interface:
`pramana.common.llm_client.{LLMSettings, ChatMessage, Completion, complete_chat}`.
No new dependency. Provider adapters still belong to their module owners.

## Guarantees and migration boundary

- OpenAI-compatible JSON chat completions at `<base_url>/chat/completions`.
  For Ollama's compatible endpoint, pass `http://localhost:11434/v1` (or
  `http://host.docker.internal:11434/v1` inside the trusted API container).
- Explicit model and endpoint; redirects refused, HTTPS required except named
  local endpoints. Retries never change model/provider or select templates.
- Per-request socket timeout, response-byte ceiling, bounded attempts and backoff.
  Retry only transport failures, HTTP 408/429 or server failures. Authentication,
  malformed/refused/truncated content and trace failures are not inference retries.
  These are request budgets, not a guarantee of a total pipeline deadline.
- Requires a run UUID and successful Langfuse authentication before inference.
  Each attempt receives a generation observation under that UUID's trace, with
  optional `insight_id`, model, parameters and exact input/output. No local fallback.
- Application logs exclude prompts, responses, keys and raw provider exception
  text. Keys use `SecretStr`; settings hide validation inputs in error messages.
- Token usage is recorded when returned. USD cost is **estimated** only when both
  caller-provided token prices and actual usage are present; otherwise None.
  Never label an unknown cost as zero or put provider prices into statistical config.
- No statistics, claim rendering, provider-role selection or verdict logic.
  Those controls remain with the current analysis and verification modules.

This branch does **not** change Rohith's or Satya's existing inference callers.
W5 and project-wide consolidation need their owner-reviewed migration. Until
then, their calls keep their existing behavior; new client guarantees cannot be
claimed for an unmigrated caller. The local analysis-proposer logging exception
does not silently apply to this strict Langfuse client.

## Consumer example (requires tester credentials)

```python
import os
from uuid import UUID

from pramana.common.llm_client import ChatMessage, LLMSettings, complete_chat

settings = LLMSettings(
    base_url=os.environ["MODEL_BASE_URL"],
    model=os.environ["MODEL_ID"],
    api_key=os.environ["MODEL_API_KEY"],
    timeout_seconds=30,
    max_retries=2,
)
completion = complete_chat(
    settings,
    [ChatMessage(role="system", content="The module owner's approved prompt"),
     ChatMessage(role="user", content="Validated schema summaries, not raw rows")],
    run_id=UUID(existing_run_id),
    insight_id=existing_insight_id,
)
text = completion.content  # Still untrusted: apply the module's existing validation.
```

Use the module's approved model/provider policy; verification must not select Gemma.
Do not print environment values or commit credentials. Existing Langfuse variables
are `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`.
Names `MODEL_*` above are consumer example inputs, not newly automatic global config.

## Tests and remaining acceptance

`tests/unit/orchestration/test_llm_client.py` covers trace linkage, usage/cost,
unavailable tracing, bounded same-model retries, refused redirects/endpoints,
response-size/timeout arguments and malformed content. These use explicit fixtures;
they do not claim successful calls to a funded provider or a live Langfuse project.

Tester: accept one approved provider and compatible local endpoint using valid
Langfuse credentials, inspect exact attempt/run linkage and usage, then accept
missing/invalid keys, provider refusal, timeout, truncated output and trace failure.
Model source still needs its existing code checks and actual statistical execution.
