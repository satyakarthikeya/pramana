"""Run both advisory steps for one run's PASS findings, with no way back to the verdicts."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import pandas as pd

from pramana.advisory.config import AdvisoryConfig, load_advisory_config
from pramana.advisory.explainer import ChatFn, explain_findings
from pramana.advisory.findings import Finding
from pramana.advisory.models import AdvisoryReport
from pramana.advisory.skeptic import review_findings
from pramana.analysis.schema_inference import SchemaProfile


def advise(
    findings: Sequence[Finding],
    frame: pd.DataFrame,
    schema: SchemaProfile,
    *,
    run_id: UUID,
    config: AdvisoryConfig | None = None,
    chat: ChatFn | None = None,
) -> AdvisoryReport:
    """Summaries and caveats for `findings`. Reads copies; changes nothing about the run."""
    config = config or load_advisory_config()
    explanations = explain_findings(
        findings, [str(c) for c in frame.columns], config.explainer, run_id=run_id, chat=chat
    )
    notes = [
        "These notes are advisory. They run after the gate and cannot change a verdict, add a "
        "claim to this run, or reach verified memory.",
    ]
    if config.skeptic.enabled:
        reviews = review_findings(findings, frame, schema, config.skeptic)
        notes.append(
            "The confound check looks at other columns for correlation, trend and "
            "group-difference findings. A column that weakens an association may be a confounder "
            "or a step between the two; the table cannot tell which. Findings of other types "
            "are listed as not checked."
        )
    else:
        reviews = []
        notes.append("The confound check is switched off in configs/analysis.yaml.")
    return AdvisoryReport(explanations=explanations, reviews=reviews, notes=notes)
