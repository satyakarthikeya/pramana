# OWNERSHIP — `requirements/`

Dependencies are split per contribution so one member's package choice can't quietly
break another's environment, and so the Docker images stay small.

| File | Owner | Installed in |
|---|---|---|
| `base.txt` | **shared — team decision to change** | everything |
| `analysis.txt` | P. Rohith | app image |
| `verification.txt` | P.P. Satya Karthikeya | app image + executor worker |
| `orchestration.txt` | B. Karthikeya | app image + worker |
| `memory.txt` | M. Karthik Reddy | app image |
| `dev.txt` | shared | local + CI only |

The root `requirements.txt` pulls all of them in for local development.

## Rules

1. **No silent dependency changes** (`AGENTS.md` §1.4). Add the package to the right file
   *and* write why — a one-line comment next to it is enough.
2. New dependency in `base.txt` = everyone's problem. Ping the team first.
3. `chromadb` belongs in `memory.txt` and nowhere else; importing it outside
   `src/pramana/memory/` fails CI.
4. Pin with `>=` while building, freeze exact versions before the final submission so the
   demo is reproducible.
5. Nothing that requires MIMIC-IV or PhysioNet credentials, ever (`AGENTS.md` §6).
