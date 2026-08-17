# OWNERSHIP — `src/pramana/contracts/`

**Owner:** P.P. Satya Karthikeya (CB.AI.U4AID23128)
**Status:** shared contract surface — owned by one, consumed by all four modules
**Schema source of truth:** `PROJECT.md` §5

## What lives here

The pydantic models that cross module boundaries:

| File | Model | Flows |
|---|---|---|
| `candidate_insight.py` | `CandidateInsight` | analysis → verification |
| `proof_object.py` | `ProofObject` | verification → memory, verification → report |
| `enums.py` | `ClaimType`, `Verdict`, `TestType` | everywhere |

## The rule that makes this folder work

**Import these models. Never redefine them.** Four members each writing their own
"insight" class is the fastest way to a broken integration two weeks before submission.
If a field you need is missing, add it here and tell the team — don't shadow the model
in your own package.

## Changing a contract

A schema change breaks other people's code by definition, so:

1. Announce it to the team before merging.
2. Update `PROJECT.md` §5 in the same change — the doc and the code do not drift.
3. Check who consumes the field (`analysis`, `memory`, `orchestration.state`) first.

## Who may edit

Satya Karthikeya writes the models. Anyone may **propose** a field; nobody adds one
silently.
