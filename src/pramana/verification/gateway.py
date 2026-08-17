"""Gateway orchestrator: batch of candidates -> generate -> execute -> collect all
raw p-values -> BH-FDR once per run -> score -> verdicts -> proof objects.

BH runs across the WHOLE batch, not per insight (AGENTS.md 3.2).

TODO(satya): SCOPE.md 4 step 7.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md
"""
