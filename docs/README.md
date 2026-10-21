# PRAMANA docs

Start with **[V1.md](V1.md)**: the MVP plan and the do-list. Everything else is reference.

## Current state and decisions

| File | What it is |
|---|---|
| [V1.md](V1.md) | The V1 MVP: user journey, work packages, do-list, plan to the review |
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | Verification gateway build state, phase by phase |
| [OPEN_ISSUES.md](OPEN_ISSUES.md) | Design issues, decisions taken, and the decision log |
| [CALIBRATION_BANDS.md](CALIBRATION_BANDS.md) | Effect-size floors: measurements, simulation, and the decision to keep them |
| [DECISIONS_LLM_ROLES.md](DECISIONS_LLM_ROLES.md) | Which model does what, and why |
| [WP7_PROPOSALS.md](WP7_PROPOSALS.md) | Small proposals awaiting a decision (outlier warning, Cramér's V) |

## [team/](team/) — checklists and guides

| File | What it is |
|---|---|
| [TEAM_GOALS_CHECKLIST.md](team/TEAM_GOALS_CHECKLIST.md) | Whole-project goals checklist (includes work past V1) |
| [DEEPSEEK_ONLY_TODO.md](team/DEEPSEEK_ONLY_TODO.md) | Current provider migration and pending live website/API acceptance |
| [DEEPSEEK_LIVE_TEST_LOG.md](team/DEEPSEEK_LIVE_TEST_LOG.md) | Real DeepSeek/browser/replay/remote trace evidence and honest coverage limitations |
| [TESTING_PHASE.md](team/TESTING_PHASE.md) | How to test the stack, including live services |
| [V1_TEST_LOG.md](team/V1_TEST_LOG.md) | Actual local V1/browser evidence, defects fixed and remaining release gates |
| [V1_REVIEW_NOTICES.md](team/V1_REVIEW_NOTICES.md) | Contract/whitelist notices and required cross-module review |
| [LLM_CLAIM_PROPOSER.md](team/LLM_CLAIM_PROPOSER.md) | How the LLM claim proposer works and its limits |

## [handoffs/](handoffs/) — history

Written when work changed hands. Useful background, not instructions.

[BENCHMARK_40_HANDOFF.md](handoffs/BENCHMARK_40_HANDOFF.md) ·
[ROHITH_HANDOFF.md](handoffs/ROHITH_HANDOFF.md) ·
[ROHITH_ANALYSIS.md](handoffs/ROHITH_ANALYSIS.md) ·
[B_KARTHIKEYA_COMPLETION.md](handoffs/B_KARTHIKEYA_COMPLETION.md) ·
[KARTHIK_LOCAL_HANDOFF.md](handoffs/KARTHIK_LOCAL_HANDOFF.md) ·
[DECISIONS_HANDOFF.md](handoffs/DECISIONS_HANDOFF.md)

## [data/](data/) — generated audit files

Benchmark build and metadata reports (JSON). Aggregate audit only; no raw data.

## [diagrams/](diagrams/)

Architecture presentation (SVG).

## Not in `docs/`

`PROJECT.md`, `SCOPE.md`, `AGENTS.md`, `OWNERSHIP.md` at the repository root define the
architecture, scope and rules.
