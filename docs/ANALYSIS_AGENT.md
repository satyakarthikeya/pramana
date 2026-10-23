# Analysis agent: workspace, tools and cost control

> Design for Phase 2 and 3. Status (23 Oct 2026): the workspace, tools, ledger, Data Reader,
> agent loop and disclosure are built and tested; see section 8. It touches `AGENTS.md` §2 (model roles), §3 (statistics rules) and §4 (execution safety),
> so it needs the verification owner's approval before merge (`AGENTS.md` §8.10).

## 1. The rule that makes it trustworthy

**The model decides what to look at. Code computes every number.**
The agent never writes a statistic from memory. It writes small Python/NumPy programs, a
sandbox runs them on the user's table, and the agent reads the printed result. Whatever it
finds is a *lead*. The verification gateway still recomputes everything from the raw table
and is the only thing that can pass a claim.

## 2. The workspace (Python and NumPy, safely)

Reuse the existing sandboxed executor instead of building a second one.

- **Where:** a subprocess in the API container (in-process mode) or in the worker container
  (isolated mode: no network, read-only filesystem, tmpfs scratch, 1 GB memory, 1 CPU).
- **Inputs:** the cleaned table as a read-only DataFrame named `df`, plus the schema.
- **Allowed imports:** `numpy`, `pandas`, `math`, `statistics`, and `pramana.verification.stats`
  (the vetted library). No `scipy`, `sklearn` or `statsmodels` directly, no network, no file
  writes outside the temp directory, same static policy as the gateway.
- **Output:** the program prints JSON. Output is capped (4 KB) and truncated with a marker, so
  the model never receives a table dump.
- **Limits:** 20 s timeout and the memory cap per execution, at most 8 executions per run.
- **Provenance:** every execution gets an ID (`x1`, `x2`, ...) and its code, output, duration
  and data hash are stored under the run. A number in any claim cites an execution ID.

## 3. Tools the agent can call

Fixed, tested functions cover the common questions so most turns need no free-form code:

| Tool | Returns |
|---|---|
| `describe(column)` | count, missing, mean, median, spread, min/max, or top categories |
| `compare_groups(value, group)` | per-group n, median, quartiles |
| `relate(x, y)` | Spearman rho and Kendall tau-b with n, descriptive only (no p-value) |
| `trend(value, order)` | Sen slope with n, descriptive only |
| `missingness(columns)` | missing counts and patterns |
| `run_python(code)` | the sandbox above, for anything the fixed tools cannot do |
| `propose_claim(...)` | a structured claim (type, variables, direction, reference group) |

Every tool has known-answer tests (a planted null gives about zero; a planted effect is
recovered). No tool returns a p-value or a verdict.

## 4. Spending: designed to be cheap by default

1. **Free first.** The rule scan already proposes claims with no model call. The agent is
   only invoked to extend that list or to answer a question, never to redo it.
2. **Compact context.** The model gets the schema, column summaries and the question, never raw
   rows. Tool results are capped, so a turn is a few thousand tokens.
3. **Hard budgets in config** (one place, `configs/analysis.yaml`): maximum turns per run (default 6),
   maximum output tokens per turn, maximum total tokens per run, maximum executions. At the
   limit the agent stops and reports what it has; it never keeps going.
4. **Stable prefix.** The system prompt and schema come first and never change within a run, so
   the provider's context caching can discount repeated input.
5. **Cache by content.** Results are keyed by dataset hash, question, model and tool version.
   Asking the same thing of the same data costs nothing.
6. **Cheap model by default** (`deepseek-flash`); the larger model is an explicit opt-in.
7. **Visible cost.** Token usage is read from the provider's response and shown in the run
   (tokens in/out, calls), with an optional per-dataset cap that blocks further calls.

## 5. Statistical honesty

- **Count everything explored.** Each hypothesis the agent examines in its workspace is logged
  to a per-dataset ledger. Either all examined hypotheses join the correction family, or the
  agent is capped at N examined hypotheses and N is the family size. Proposing the best 8 of 200
  privately tested pairs would otherwise understate the multiple-testing burden.
- **Hold-out option.** Explore on a random half of the rows and let the gateway test on the
  other half. Needs a decision: it halves the sample for every claim.
- **Agreement check (diagnostic only).** Compare the agent's exploratory effect with the
  gateway's effect for each claim. A large gap is logged and shown as a warning. It never
  changes a verdict.
- **No silent fallback.** If the model, its credentials or tracing are unavailable, the run
  records an explicit error. It never substitutes a different method quietly.

## 6. What stays unchanged

The admissibility screen, the sandbox policy for gateway code, permutation tests, one
Benjamini-Hochberg family per run, effect floors, the gate, proof objects and the PASS-only
memory guard. The agent only changes which claims reach the gateway and how well-founded they are.

## 7. Open decisions

1. Ledger policy: count all explored hypotheses, or cap the number the agent may examine.
2. Hold-out split: adopt, or leave it as a later option.
3. Tracing: `AGENTS.md` §2 allows local tracing only for the claim proposer. Extend that
   authorization to the analysis agent, or provide Langfuse credentials.
4. Default budget numbers after one measured run on real data.

## 8. What is built, and what is not

| Part | State |
|---|---|
| Tested tools: `describe`, `compare_groups`, `relate`, `trend`, `missingness`, `scan_pairs` | built; known-answer tests, descriptive only, never a p-value |
| Python workspace (numpy/pandas on a copy, no files, no network, bounded output) | built; static policy plus subprocess, timeout and memory cap on POSIX |
| Exploration ledger with exact counts, shown with results | built |
| Data Reader (counted facts, missing codes, outliers, NHANES labels) | built, code only, no model |
| Analyst loop with hard budgets (turns, tool steps, Python runs, tokens, hypotheses) | built and tested against scripted replies; **not yet run against live DeepSeek** (needs Langfuse keys) |
| Transcript per run for audit | built (`data/runs/<run>/agent_transcript.json`) |
| Ledger counted into the correction family | **not done**: disclosed instead, because changing the family is a statistics-rule decision (open decision 1) |
| Hold-out split, cross-run cache, per-dataset spending cap | not built |

Deviations from section 4: the cost controls are per-run only. Free-form Python steps count
as zero examined hypotheses, because what they examine cannot be audited, and are reported
separately. The Python check is an adherence check, not a security boundary: in the
in-process API container it shares a filesystem with the server, so file helpers are blocked
by name; the isolated worker container adds a read-only filesystem and no network.
