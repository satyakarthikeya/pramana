# data/

**Gitignored. Nothing in here is committed** (`AGENTS.md` §6).

Suggested local structure:

```
data/
  raw/          downloaded source datasets (NHANES, NFHS-5, other open data)
  benchmark/    the 40 curated evaluation datasets
  demo/         the demo subset with the injected false correlation
  tmp/          executor scratch space
```

## Rules

- **MIMIC-IV is forbidden** — PhysioNet's zero-retention policy conflicts with this
  pipeline. NHANES / NFHS-5 / other open-access data only.
- The benchmark excludes famous datasets (Iris, Titanic, …) — they test the model's
  memory, not our pipeline.
- Datasets are reproduced by the download/curation scripts in `scripts/`, not by passing
  files around.

Curation is P. Rohith's scope (`scope/SCOPE_P_Rohith.md` §2 item 6).
