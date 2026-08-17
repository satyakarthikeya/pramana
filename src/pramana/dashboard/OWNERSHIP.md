# OWNERSHIP — `src/pramana/dashboard/`

**Owner:** M. Karthik Reddy (CB.AI.U4AID23131)
**Module:** Memory & System Deployment (visualisation)
**Scope file:** `scope/SCOPE_M_Karthik_Reddy.md` §2 item 7

## What lives here

Run visualisation and the demo view.

- **Run view:** every candidate insight with verdict, p-value, q-value, effect size,
  evidence score. PASS vs REJECT visually unmistakable.
- **Demo view (the centerpiece):** the planted false correlation being REJECTed side by
  side with a real published relationship PASSing — both with proof objects on screen.
- **Memory view:** stored lessons with provenance back to their `insight_id`.

## Who may edit

M. Karthik Reddy only.

## Boundaries

- Read-only. The dashboard renders stored results; it never triggers a memory write and
  never computes a statistic of its own.
- It must render a completed run **without manual data massaging** — if the data needs
  hand-editing to look right, fix the pipeline, not the view.
- No verdict is ever softened for presentation. A REJECT is displayed as a REJECT.

## Frontend stack

Not fixed by any scope file — the owner's call. Whatever it is, it consumes the API in
`src/pramana/api/`, not the database directly.
