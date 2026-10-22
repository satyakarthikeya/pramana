# STATUS.md — where we are (22 October 2026)

> Sources: `docs/V1.md`, `docs/team/V1_TEST_LOG.md`, git history. Figures are from the
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
- [ ] Close the DeepSeek-only follow-ups in `docs/team/DEEPSEEK_ONLY_TODO.md`; read `DEEPSEEK_LIVE_TEST_LOG.md` (it records an extra decoy-coverage check that did not pass)
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

## Known limitations

See `SCOPE.md` §6.
