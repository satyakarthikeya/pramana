# OWNERSHIP.md — who owns which folder

> Master map of the repository. Source of truth for module ownership is
> `PROJECT.md` §4; this file only projects that onto directories.
> Every package also carries its own `OWNERSHIP.md` with the details.

## Rule

**You edit your own folders. You import everyone else's.**
Touching another member's folder needs their sign-off first (`AGENTS.md` §1.2, §1.3).

## Map

| Path | Owner | Roll | Scope file |
|---|---|---|---|
| `src/pramana/contracts/` | P.P. Satya Karthikeya | CB.AI.U4AID23128 | `SCOPE.md` |
| `src/pramana/verification/` | P.P. Satya Karthikeya | CB.AI.U4AID23128 | `SCOPE.md` |
| `src/pramana/evaluation/` | P.P. Satya Karthikeya | CB.AI.U4AID23128 | `SCOPE.md` (later work item) |
| `src/pramana/analysis/` | P. Rohith | CB.AI.U4AID23123 | `scope/SCOPE_P_Rohith.md` |
| `src/pramana/orchestration/` | B. Karthikeya | CB.AI.U4AID23109 | `scope/SCOPE_B_Karthikeya.md` |
| `src/pramana/common/` | B. Karthikeya | CB.AI.U4AID23109 | `scope/SCOPE_B_Karthikeya.md` |
| `src/pramana/memory/` | M. Karthik Reddy | CB.AI.U4AID23131 | `scope/SCOPE_M_Karthik_Reddy.md` |
| `src/pramana/api/` | M. Karthik Reddy | CB.AI.U4AID23131 | `scope/SCOPE_M_Karthik_Reddy.md` |
| `src/pramana/dashboard/` | M. Karthik Reddy | CB.AI.U4AID23131 | `scope/SCOPE_M_Karthik_Reddy.md` |
| `docker/` | B. Karthikeya (builds) → M. Karthik Reddy (deploys) | — | shared tooling, see `docker/OWNERSHIP.md` |
| `configs/` | per file — see `configs/OWNERSHIP.md` | — | — |
| `tests/` | mirrors `src/` ownership — see `tests/OWNERSHIP.md` | — | — |
| `requirements/` | per file — see `requirements/OWNERSHIP.md` | — | — |
| `data/` | nobody (gitignored) | — | `AGENTS.md` §6 |
| `scripts/`, `notebooks/`, `docs/` | shared | — | — |

## Shared files (change = team decision)

`PROJECT.md`, `AGENTS.md`, `OWNERSHIP.md`, `pyproject.toml`, `requirements/base.txt`,
`src/pramana/contracts/**` — the contracts are owned by Satya Karthikeya but consumed by
all four modules, so a schema change is announced before it is merged, never after.

## Direction of dependency

```
contracts  ←  imported by everyone, imports nobody
common     ←  imported by everyone
analysis   →  contracts, common
verification → contracts, common          (imports NO other member's module)
memory     →  contracts, common, verification.memory_guard
api        →  memory, orchestration
orchestration → all of the above (the spine — it calls, others don't call it)
```

If you find yourself needing an import that points the other way, that is an interface
problem — raise it, don't work around it.

## The one rule that outranks ownership

`memory_write ⟹ verdict == PASS` (`AGENTS.md` §0). No folder, no owner, no deadline
justifies a path around the verification gateway.
