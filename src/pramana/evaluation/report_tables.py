"""Result tables for the capstone report: per-condition precision, recall and FDR, with n.

n=40 gives thin statistical power, so every table carries that caveat in its own text
and reports DIRECTIONAL trends, not significance (PROJECT.md 6). The empirical FDR is
shown only for conditions that have a gate whose nominal level it can be compared with;
for the others the column is `None`, not zero.

This module produces tables (a dict list and markdown) only. Report PROSE is written by
humans (AGENTS.md 7).

Owner: P.P. Satya Karthikeya
Scope: src/pramana/evaluation/SPEC.md 3
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from pramana.evaluation.metrics import DatasetScore, aggregate_scores

#: Conditions whose SUPPORTED set has a nominal FDR level to be compared against.
GATED_CONDITIONS: frozenset[str] = frozenset({"D"})

_COLUMNS = (
    "condition",
    "n_datasets",
    "n_reported",
    "precision",
    "recall",
    "empirical_fdr",
    "nominal_alpha",
)


class ReportTable(BaseModel):
    """One row per condition, plus the caveat that travels with every table."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rows: list[dict[str, Any]]
    caveat: str

    def to_markdown(self) -> str:
        """The table as markdown, caveat underneath."""

        def cell(value: Any) -> str:
            if value is None:
                return "n/a"
            return f"{value:.3f}" if isinstance(value, float) else str(value)

        lines = [
            "| " + " | ".join(_COLUMNS) + " |",
            "|" + "|".join("---" for _ in _COLUMNS) + "|",
        ]
        lines += ["| " + " | ".join(cell(row[c]) for c in _COLUMNS) + " |" for row in self.rows]
        return "\n".join(lines) + "\n\n" + self.caveat + "\n"


def build_report_table(
    scores_by_condition: Mapping[str, Sequence[DatasetScore]], *, alpha: float
) -> ReportTable:
    """Build the per-condition table from per-dataset scores.

    Guarantees: precision and recall are pooled counts (undefined stays `None`);
    `empirical_fdr` is the mean per-dataset false discovery proportion and is present
    only for gated conditions, next to the nominal `alpha` it is compared with.
    """
    rows: list[dict[str, Any]] = []
    for condition, scores in scores_by_condition.items():
        agg = aggregate_scores(scores)
        gated = condition in GATED_CONDITIONS
        rows.append(
            {
                "condition": condition,
                "n_datasets": agg.n_datasets,
                "n_reported": agg.n_reported,
                "precision": agg.precision,
                "recall": agg.recall,
                "empirical_fdr": agg.mean_fdp if gated else None,
                "nominal_alpha": alpha if gated else None,
            }
        )
    n_values = sorted({row["n_datasets"] for row in rows})
    caveat = (
        f"Directional trends only: n = {', '.join(map(str, n_values))} datasets gives thin "
        f"statistical power and these figures are not significance tests (PROJECT.md 6). "
        f"Precision counts a hit only with the correct direction; empirical FDR is the "
        f"mean per-dataset false discovery proportion of the gated set."
    )
    return ReportTable(rows=rows, caveat=caveat)
