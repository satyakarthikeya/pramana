# STATUS.md — where we are (22 October 2026)

> Sources: `docs/V1.md`, `docs/evidence/V1_TEST_LOG.md`, git history. Figures are from the
> repo's own logs; they were not re-run when this file was written.

## Branches

| Branch | State |
|---|---|
| `main` | at `2a436ec`: PR #25 (V1 product) and PR #26 (DeepSeek-only) merged |
| `feat/b-karthikeya/deepseek-only` | merged via PR #26 |
| `review/v1-product` | local review branch, same V1 content as `main` |
| other `feat/*` branches | older work already folded into V1 or superseded; check before deleting |

## V1 state

**Done and tested**
- Local app: `python -m pramana`, in-process verification, 8-candidate cap per run.
  Since PR #26 the live profile uses DeepSeek for proposals and falsification code
  (template/rule modes remain explicit offline options). The test figures below predate
  that and were recorded on the keyless setup
- Upload with friendly errors, preview, stage and per-claim progress
- Gateway: admissibility screen, sandbox, permutation tests, one BH-FDR family, effect floors,
  gate, proof objects
- Dashboard: finding cards with strength words, readable and raw proofs, "Not a finding" reasons,
  JSON/CSV export, sample dataset, memory panel with source links, historical hints
- PASS-only memory (API, graph, gateway and memory tests assert it)
- README, `.env.example`
- Full suite 771 passed (414 s) at last log; ruff, mypy, `pip check` clean
- Headless-Chrome journey on two datasets passes. Planted check: true pair PASS, shuffled decoy REJECT

**Open before the 27 Oct review**
- [ ] Clean-clone test on a second machine (A5)
- [ ] Full suite and ruff green on `main` after merge (G2)
- [ ] Affected owners acknowledge the review notices (PR #25 comment)
- [ ] Close the DeepSeek-only follow-ups in `docs/team/DEEPSEEK_ONLY_TODO.md`; read `docs/evidence/DEEPSEEK_LIVE_TEST_LOG.md` (it records an extra decoy-coverage check that did not pass)
- [ ] Confirm Langfuse credentials work: a DeepSeek key alone is not enough under the tracing rules
- [ ] `docs/V1.md` and the V1 test log still describe the earlier template/Gemma setup (historical)
- [ ] Independent human rehearsal of the journey
- [ ] Optional: one real hosted-model proposer run with a key, recording cost and claims (C2)
- [ ] Report text, written by humans (G6)
- [ ] Code freeze, end of Mon 26 Oct

## Housekeeping done today

Removed the per-person scope files (`scope/`), root `OWNERSHIP.md` and
`verification_gateway_plan_prompt.md`; rewrote `PROJECT.md` and `SCOPE.md`; added this file.
Not yet committed. Code comments and the `OWNERSHIP.md` files under `src/`, `configs/`,
`docker/` and `requirements/` still cite the old scope files and are untouched.
`AGENTS.md` §8.10 still speaks of module owners.

## Workspace UI and chat branches (23 October 2026, not on `main`)

Two branches, to be merged in this order (the second branches from the first):

| Branch | Commits | What |
|---|---|---|
| `feat/team/workspace-ui` | `a09f89a` `4aff983` `78011fd` `675e42f` `65c5d8e` | accounts, datasets, Data Reader, analysis workspace and agent, web UI, Docker + nginx |
| `feat/team/chat-agent` | `2c96a8a` `7d45c10` `914a99d` `dd51937` `3e3fd3b` `45a24f7` | Phase 4: "talk to your data" backend, Ask tab, two review rounds of fixes |

`7d45c10` is not green on its own (its ledger-numbering test failed under contention); `dd51937` fixes it.

| Branch | What |
|---|---|
| `feat/team/skeptic-explainer` (from `chat-agent`; merge third) | Phase 5: the Skeptic and the Explainer for PASS findings. `1271065` `2a89ec7` `8c67e6f` `75c6d20`, then the rounding/compose commit and a docs commit (see `git log`) |

**Phase 5 in one paragraph.** After the gate, each PASS finding gets a plain-language sentence (the
Explainer) and a confound check (the Skeptic). Both run after every proof exists, read copies, and cannot
change a verdict, the status, the correction family or memory; a crash leaves the results unchanged. The
Skeptic is code only (rank partial associations; descriptive caveats and questions for a NEXT run; "not
checked" is never shown as clean; 20 s wall-clock budget). The Explainer writes the sentence by code from
the proof by default; `PRAMANA_EXPLAINER_ENGINE=api` (now exposed in `docker/docker-compose.yml`, default
`template`) lets DeepSeek word it for correlation and trend findings only, checked by code (effect and rows
as the only numbers, declared direction must match the sign, no causal or verdict wording), with the facts
line and the disclaimer added by code and every fallback recorded and shown.

**Verified by running (Phase 5):** full suite exit 0 at `75c6d20`; in Docker the analysis journey gives
3 verified and 2 rejected offline and 3 verified and 1 rejected on the live model profile (DeepSeek proposals
and test code, traced in Langfuse); the Findings screen keeps its ordinary wording; the model-worded
Explainer was tried live under the stricter rules and all three sentences were accepted; two independent
read-only reviews (no critical issue; their high and medium findings were fixed and tested).

**Not verified (Phase 5):** keyboard-only, 800 px and grayscale passes; mypy; web unit tests (none exist);
the Skeptic's time budget only with a fake clock (not on a very large table end to end); live-run cost (a
live run took about 112 s and tokens were not priced); one live run failed closed once with "Langfuse
authentication is unavailable" right after a container restart and passed on retry (transient, nothing was
published).

**Needs the verification owner:** the Skeptic's statistics and every threshold under `advisory.skeptic`
(including `max_duplicate_group_link` and `time_budget_seconds`), the Explainer bullet in AGENTS.md section 2,
and whether model-worded sentences should ever be on by default.

**Not built:** a lesson-curator agent, per-user verified memory (still shared across accounts), a hold-out split,
and counting chat or exploration in the BH family.

**The Docker stack is left on the live profile** (engine `api`, generator `llm`, Explainer `template`). The
offline overlay (`docker-compose.offline.yml`) is only for testing without keys and shows "rule scan, no model".

**Verified by running:** full suite exit 0 at `45a24f7` (0 failures), `ruff` clean, web build clean;
in Docker (offline profile, chat on live DeepSeek + Langfuse EU): the analysis journey gives
3 verified and 2 rejected, the Findings screen keeps its ordinary wording, chat answers about 15
real questions, a second account gets 404 on every chat route; two independent read-only reviews.

**Not verified:** keyboard-only pass, 800 px width and grayscale pass of the Ask tab; mypy on the new
modules; any web unit tests (none exist); chat cost (no token prices are configured; one question
is roughly 2,500 to 5,800 tokens). Live chat has been tried on a small number of questions only.

**Needs a decision / the verification owner (AGENTS.md section 8.10):**
- The chat bullet added to AGENTS.md section 2, and chat's statistics: each chat claim is a family of one
  (q equals p), disclosed as asked after seeing results; whether chat claims should ever join a BH family is open.
- For "differs by" questions the model chooses the direction, so a real difference can come back Rejected
  because the guess was wrong. Fixing it means choosing direction after seeing the data.
- Group labels show raw codes ("1.0") where the Data Reader knows the meaning.
- Verified memory is still shared across accounts; a QA run's lessons must be removed from Chroma by run id.
- The chat hourly cap and in-flight counter are per server process.

## Known limitations

See `SCOPE.md` §6.
