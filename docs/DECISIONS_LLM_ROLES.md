# Decision record: where LLMs sit in PRAMANA

> Date: 18 September 2026
> Recorded by: P.P. Satya Karthikeya (verification module)
> Design it produces: `PROJECT.md` §2–§3 and `AGENTS.md` §2
> Status of each item is stated on the item. "Decided" means decided by the owner of the
> module it touches; anything touching another member's module is "Proposed" until that
> member agrees (`AGENTS.md` §1.3, §8.7).

## Why this record exists

The first design (`PROJECT.md`, August) said PRAMANA is "an LLM agent that analyzes
datasets", verified by a gateway running on DeepSeek V4, with Gemma for routine
sub-agent work. What got built drifted from that:

- the analysis module became a deterministic scan with no model, because
  `scope/SCOPE_P_Rohith.md` §2.4 specified scan strategies, not an LLM;
- the gateway's DeepSeek path was built but made optional, with a template
  generator as the default (`docs/OPEN_ISSUES.md` issue 4, 2 September);
- no Gemma component was built.

The result, confirmed on 18 September: **the system as built calls no model at all.**
The first end-to-end run (NHANES demo, `scripts/run_demo.py` on branch
`feat/team/one-dataset-e2e`: 34 candidates, 29 PASS, 5 REJECT) was entirely
deterministic. That proves the gateway works, but it does not test the project's claim,
because nothing hallucinates a claim for the gateway to catch.

## The principle

**Models propose and write code; code decides.** An LLM may propose a claim or write
the program that tests it. Every statistic, q-value and verdict comes from our own
tested code, and no model output is ever treated as evidence. `AGENTS.md` §2 turns this
into rules.

## Decisions

### D1. DeepSeek writes every falsification test — Decided (verification owner)

DeepSeek V4 becomes the default generator of `falsify(frame)` for every claim. Its code
may only call `pramana.verification.stats`.

**Why.** A template is one fixed test per claim type. It cannot adapt to a particular
claim or dataset (a subgroup claim, a unit inside a column, a code like `0` meaning
"not measured"). Such claims either come back NOT_TESTABLE or get tested on the wrong
values. DeepSeek writes the test each claim needs.

**Why trust is unaffected.** DeepSeek's code is checked before it runs (parses, defines
`falsify(frame)`, uses the configured seed and permutation count, imports only the
whitelist). Every number must carry an HMAC stamp that only our library can produce, and
the effect size must equal the stamped statistic. The p-value, BH correction, gate and
verdict are code.

**What it supersedes.** Only the "template is the DEFAULT generator" part of:
`docs/OPEN_ISSUES.md` issue 4 and decision-table row 4, and `docs/DECISIONS_HANDOFF.md`
A.2 and A.4. The rest of those decisions stands: the trust guarantee comes from the
sandbox, whitelist and stamp, not from the choice of model.

**The template generator stays**, as the reference the DeepSeek path is measured against
and as an explicit offline mode. It is chosen in config, never used as a silent fallback.

**The one gap D1 opens, and its fix.** The stamp proves a number came from our library.
It does not prove the code tested the right columns: LLM-written code could use another
column, filter to an unstated subgroup, or drop awkward rows, and still produce a valid
stamp. Two checks close this (W1, W8 below). Until W1 exists, the DeepSeek default
must not be switched on for anything that reaches a user.

### D2. An LLM analysis agent proposes the claims — Proposed (needs P. Rohith)

The analysis step becomes an LLM that reads the schema profile, column summaries, the
user's question and retrieved lessons, and proposes **structured** claims
(`claim_type`, `variables`, direction, reference group). Code renders each claim
sentence from a hedged template, validates it against the `CandidateInsight` contract,
and drops any claim naming a missing column or an unsupported type. The batch cap stays.

**Why.** It is the original design, and it is what gives the gateway something real to
catch. It also makes the evaluation meaningful: conditions B, C and D (`PROJECT.md` §6)
all assume an agent that proposes claims.

This changes `scope/SCOPE_P_Rohith.md` §2.4 and §4, which specify deterministic scan
strategies. That file is Rohith's, so it has not been edited here.

### D3. Model rules — Decided for the verification module, Proposed elsewhere

Recorded in `AGENTS.md` §2: DeepSeek writes test code only; the analysis LLM proposes
structured claims and never authors claim text or evidence; Gemma labels or suggests
and never edits data; no silent model substitution; every call traced in Langfuse.

## Work required before `PROJECT.md` §2 is true

Each item has one owner. Update the status table in `PROJECT.md` §2 in the same PR that
completes an item.

| # | Work | Owner | Blocks |
|---|---|---|---|
| W1 | **Column check:** refuse generated code that reads any column outside the claim's `variables`, or filters rows the claim does not state | Satya | switching D1 on |
| W2 | Pin every test that calls `verification.config.load_config()` to `generator: template`, so the suite stays offline and deterministic | Satya | W3 |
| W3 | Switch `configs/verification.yaml` `llm.generator` to `llm`; demo and CI need `DEEPSEEK_API_KEY` (already listed in `.env.example`) | Satya | — |
| W13 | **Split generation from execution in deployment.** The Celery worker has no internet access by design (`docker/README.md`), so DeepSeek cannot be called from inside it. Code generation (and its Langfuse export) must run in a trusted process with internet access, and only the generated program goes to the isolated worker. Local in-process runs are unaffected | B. Karthikeya (Satya reviews) | W3 in any deployed setup |
| W4 | One shared, OpenAI-compatible LLM client in `pramana.common` (DeepSeek, Ollama/Gemma, any API), with timeouts, retries, cost logging and Langfuse tracing under `run_id` | B. Karthikeya | W5, W6 |
| W5 | Move the DeepSeek generator onto W4's client. It currently builds its own Langfuse client (`falsification/generator.py`), so its traces are not tied to the run's trace | Satya | — |
| W6 | The LLM analysis agent (D2): prompt, JSON-schema output, contract validation, templated claim text | P. Rohith | the demo, the evaluation |
| W7 | Gemma `SemanticRefiner` for schema inference, and cleaning suggestions applied and logged by code | P. Rohith | — |
| W8 | **Agreement check:** where a template exists for the claim type, also run the template test and flag any verdict that differs from DeepSeek's. Doubles as the D1 comparison in the evaluation | Satya | — |
| W9 | Report lists rejected claims separately with their gate outcome, p and q (today it shows PASS only) | B. Karthikeya | — |
| W10 | Memory: ChromaDB store, lesson abstraction, embedding retrieval; retrieved lessons reach the analysis agent as hints only, never as reported insights | M. Karthik Reddy | episode mode |
| W11 | Demo: check that the analysis agent actually proposes the injected false signal; redesign the injection if it does not (`PROJECT.md` §7) | P. Rohith | the demo |
| W12 | Evaluation: run D with both generators; log model and generator per run (`src/pramana/evaluation/SPEC.md` §5 already requires it) | Satya | — |

## Open questions for the team

| # | Question | Recommendation |
|---|---|---|
| Q1 | Which model runs the analysis agent? | Configurable. Start with Gemma through Ollama (free, local, already in `.env.example`); move to an API model by config if its structured output is unusable. |
| Q2 | What does the analysis LLM see? | The schema profile and per-column summaries. **Not** the correlation matrix: an agent that reads it only copies the scan, and the gateway then has nothing to catch. **Not** raw rows: privacy and cost. |
| Q3 | Keep evaluation condition C (LLM critic, no execution)? | Keep it. D vs C is the result that shows execution beats LLM judgement (`docs/OPEN_ISSUES.md` issue 3). Without C the evaluation shows only that a gate beats no gate, and the report must then claim only that. |
| Q4 | What if the DeepSeek API is down on demo day? | Every claim fails closed as NOT_TESTABLE, by design. Prepare a second demo run with `llm.generator: template`, labelled as the offline mode, never swapped in silently. |
| Q5 | Subgroup claims ("among adults over 60, …") | Need a contract change (`CandidateInsight` has no filter field), a matching rule in W1, and vetted support in the stats library first. Later work item, not part of D1. |

## Files deliberately not edited

These belong to other members. Each needs its owner to update it to match D1–D3:

- `scope/SCOPE_P_Rohith.md` §2.4, §4 — analysis becomes an LLM agent (D2, W6, W7, W11)
- `scope/SCOPE_B_Karthikeya.md` — shared LLM client (W4) and report change (W9)
- `scope/SCOPE_M_Karthik_Reddy.md` — retrieved lessons are hints only (W10)
