# PRAMANA docs

Current project state is in [../STATUS.md](../STATUS.md). Architecture is in
[../PROJECT.md](../PROJECT.md), scope in [../SCOPE.md](../SCOPE.md), and the rules for
contributors in [../AGENTS.md](../AGENTS.md). This folder holds the rest.

Next work, in order, is in [ROADMAP.md](ROADMAP.md).

## Current

| File | What it is |
|---|---|
| [V1.md](V1.md) | The V1 plan and do-list |
| [DESIGN_verification_gateway_v3.md](DESIGN_verification_gateway_v3.md) | Gateway v3 design, awaiting owner sign-off |
| [GATEWAY_V3_STATUS_AND_SIGNOFF.md](GATEWAY_V3_STATUS_AND_SIGNOFF.md) | Gateway v3 status and the sign-off sheet |
| [PLAN_analysis_platform.md](PLAN_analysis_platform.md) | V2 platform plan (evidence levels, exploration/confirmation split) |
| [PLAN_data_analyst.md](PLAN_data_analyst.md) | Data-analyst layer plan |
| [ANALYST_LAYER_STATUS.md](ANALYST_LAYER_STATUS.md) | Status of the analyst layer (PR 31) |
| [EVALUATION.md](EVALUATION.md) | Parked V2 evaluation plan |
| [OPEN_ISSUES.md](OPEN_ISSUES.md) | Decision log and open design issues |
| [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) | Gateway build state (historical snapshot) |

## Design and decision records

[ANALYSIS_AGENT.md](ANALYSIS_AGENT.md) · [CALIBRATION_BANDS.md](CALIBRATION_BANDS.md) ·
[DECISIONS_LLM_ROLES.md](DECISIONS_LLM_ROLES.md) · [SHARED_LLM_CLIENT.md](SHARED_LLM_CLIENT.md) ·
[WP7_PROPOSALS.md](WP7_PROPOSALS.md) (proposals awaiting a decision)

## [team/](team/) — guides and checklists

[TESTING_PHASE.md](team/TESTING_PHASE.md) (how to test, including live services) ·
[DEEPSEEK_ONLY_TODO.md](team/DEEPSEEK_ONLY_TODO.md) (pending live acceptance) ·
[TEAM_GOALS_CHECKLIST.md](team/TEAM_GOALS_CHECKLIST.md) ·
[V1_REVIEW_NOTICES.md](team/V1_REVIEW_NOTICES.md)

## [evidence/](evidence/) — test logs and generated reports

[V1_TEST_LOG.md](evidence/V1_TEST_LOG.md) and
[DEEPSEEK_LIVE_TEST_LOG.md](evidence/DEEPSEEK_LIVE_TEST_LOG.md) record what was run and
what was not. `evidence/benchmark/` holds the benchmark build and metadata JSON written by
`scripts/build_benchmark_pilot.py` (aggregate audit only, no raw data).

## [diagrams/](diagrams/)

`PRAMANA_architecture_presentation.svg` is the exported figure. `source/` holds the
editable `.excalidraw` files. There are two gateway-flow sources:
`pramana-gateway-flow.excalidraw` (larger) and `pramana-gateway-flow-compact.excalidraw`.

## [archive/](archive/) — history, not current

Session handoffs ([handoffs/](archive/handoffs/)), the last session handoff, a cloud-session
prompt, and the historical LLM claim proposer record. Useful background, not instructions.
Some status documents above (IMPLEMENTATION_STATUS.md, OPEN_ISSUES.md) are also historical
in parts and say so in a banner.
