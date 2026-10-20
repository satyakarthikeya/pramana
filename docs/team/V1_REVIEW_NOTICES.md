# V1 coordination notices (G5)

To the analysis, verification, workflow and memory/API owners: these notices are
published with the V1 product pull request for shared review, not a unilateral
change to authoritative contracts or statistical policy.

## Existing `reference_group` contract field

`src/pramana/contracts/candidate_insight.py` already carries optional
`reference_group: str | None`: which category level a group-difference claim is
about. Consumers must preserve it with `asserted_direction`, rather than dropping
it while serializing a candidate or regenerating claim text from unrelated data.
It distinguishes a directed comparison from an undirected group-difference claim.
The gateway remains the owner of admissibility, permitted comparisons and verdicts.
This V1 PR adds no new field to `src/pramana/contracts/` and changes no proof schema.
Please acknowledge the existing shared field in the consumer owners' review.

## Execution whitelist wording

The current checked-in `AGENTS.md` section 4 already permits only `numpy`, `pandas`
and `pramana.verification.stats` in generated programs, and explicitly distinguishes
the vetted module's internal SciPy use from generated code importing SciPy directly.
That is consistent with the present executor policy and design. The historical
contradiction noted in the V1 plan must not be "fixed" by relaxing the whitelist.
Verification-owner confirmation is requested; no AGENTS section was renumbered or
rewritten, no import allowance added and no sandbox limit relaxed in this PR.

## Additional V1 coordination

The user explicitly requested all V1 software tasks, including cross-module UI/API
work. Review is still ownership-based under AGENTS section 8: API/dashboard and
`configs/memory.yaml` need the memory/deployment owner; proposal cap integration
needs analysis/workflow review; memory/verification integration always needs Satya.
The V1 application profile explicitly selects offline template execution by default;
the standalone verification configuration keeps its owner-approved LLM default.
No paid-model substitution, new inference dependency or statistical threshold
change is hidden in this profile.
