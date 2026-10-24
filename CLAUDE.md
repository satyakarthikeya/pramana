# CLAUDE.md

PRAMANA: drop a table, get an analyst-style report with three evidence levels
(Exact = code arithmetic, Measured = models scored on held-out rows, Tested = the
verification gateway). Models propose; code computes and decides.

## Read first, in this order

1. `STATUS.md`: where things stand, known limits, stale text still to fix.
2. `docs/ROADMAP.md`: what is in review, what comes next in order, proposed AGENTS.md changes.
3. `AGENTS.md`: the rules. They override everything here.
4. `PROJECT.md`: workflow (§2), contracts (§5), package map (§9), run and test (§10).

## Five rules that matter most

1. `memory_write ⟹ verdict == PASS`. Never add a path around the memory guard. FRAGILE is a REJECT.
2. p-values, FDR, the split, the sandbox, gate thresholds and model roles need the
   verification owner's approval (AGENTS.md §8.10). Flag, do not merge.
3. DeepSeek only, traced in Langfuse, fail closed; no silent fallback between `llm` and
   `template`. Thresholds and seeds live in `configs/`.
4. One task, one branch (`<type>/<owner>/<short-task>`), PR to `main`, Conventional
   Commits, full suite before committing. Never push to `main`.
5. Never commit data, `.env`, keys or personal details; stage explicit paths. Never
   renumber sections of AGENTS.md, PROJECT.md §1-§8 or SCOPE.md §2-§7 (code cites them).

## Commands

```bash
pip install -r requirements.txt && pip install -e .
(cd web && npm ci && npm run build)
python -m pramana --port 8080          # needs DEEPSEEK_API_KEY + Langfuse keys in .env
python -c "import pramana; print(pramana.__file__)"   # confirm which tree is installed
python -m pytest                       # full suite
python -m pytest --collect-only -q | tail -1          # test count
python -m ruff check .
python scripts/calibration/analyst_recall.py --top 8  # planted-fact recall (Exact)
python scripts/calibration/gate_report_card.py --reps 100   # gate FPR / power / false-kill
```

Offline run: `PRAMANA_ANALYSIS_ENGINE=deterministic PRAMANA_VERIFICATION_GENERATOR=template
PRAMANA_LANGFUSE_ENABLED=false`. Demo profile: `PRAMANA_ANALYSIS_ENGINE=planner` and
`PRAMANA_VERIFICATION_GENERATOR=template` (`.env.example` sets `llm`; override it).

## Where the current work is

- `main` has everything through PR #31 (analyst layer, gateway v3).
- `chore/satya/cleanup-for-review`: docs and lint cleanup, PR not yet opened.
- Next items: `docs/ROADMAP.md` §2, starting with tested claims for segment growth,
  concentration and forecast-vs-baseline (owner sign-off needed).
- Gateway code: `src/pramana/verification/`; Exact: `src/pramana/analysis/computed/`;
  Measured: `src/pramana/analysis/measured/`; planner: `src/pramana/analysis/planner/`;
  UI: `web/src/components/`; config: `configs/verification.yaml`, `configs/analysis.yaml`.
- Thesis report prose is human-written (AGENTS.md §7); give outlines only.
