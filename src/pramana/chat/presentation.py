"""Readable descriptive facts from stored tool outputs, never from rejected model prose."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any

from pramana.analysis.sectors import detect_sector, load_packs
from pramana.chat.models import Evidence

LEGACY_WITHHELD_TEXT = (
    "The wording the model proposed could not be checked against the tool results, "
    "so it is not shown. The results it used are listed below."
)


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def asks_about_dataset(question: str) -> bool:
    """Recognise requests for dataset meaning without capturing column calculations."""
    return bool(re.search(
        r"\b(?:what(?:'s| is| does)?\s+(?:this |the |my )?(?:data(?:set)?|table)"
        r"\s+(?:is |actually )?(?:about|represent|contain|mean)|"
        r"(?:describe|explain|summari[sz]e)\s+(?:this |the |my )?(?:data(?:set)?|table)|"
        r"(?:data(?:set)?|table)\s+(?:overview|description|purpose))\b",
        question, re.IGNORECASE,
    ))


def _meaning(names: list[str]) -> list[str]:
    """Offer a labelled vocabulary hint, never an asserted source or row identity."""
    match = detect_sector(names, load_packs())
    if match.sector == "general":
        return [
            "I can't reliably tell what this dataset is about from the available column names. "
            "They do not establish a clear subject or what each row represents.",
            "A dataset description or codebook would help identify its subject, what each row "
            "represents and why the data was collected.",
        ]
    meanings = {
        "systolic_bp": "systolic blood pressure",
        "diastolic_bp": "diastolic blood pressure",
    }
    hints = list(dict.fromkeys(
        meanings.get(role, role.replace("_", " ")) for role in match.roles.values()
    ))
    selected = hints[:6]
    basis = ", ".join(selected[:-1]) + " and " + selected[-1] if len(selected) > 1 else selected[0]
    return [
        f"The column names suggest this is a {match.label.lower()}-related dataset, "
        f"with fields for {basis}. This is a tentative interpretation of the names.",
        "I can't confirm its original purpose, what each row represents, who collected it, "
        "or whether it contains real or synthetic records from the table alone. "
        "A dataset description or codebook is needed to confirm that context.",
    ]


def computed_summary(
    evidence: Sequence[Evidence], *, max_chars: int, question: str = "",
) -> str | None:
    """Render only known descriptive fields from successful tools, or return no summary.

    No statistical decision, model text or asserted dataset origin is introduced.
    Introductions label sector vocabulary matches as tentative interpretations.
    Unknown tool payloads remain available as evidence, not paraphrased.
    """
    lines: list[str] = []
    # Prefer a table introduction over separate column summaries when both are available.
    ordered = sorted(evidence, key=lambda e: e.tool != "overview")
    if asks_about_dataset(question):
        names: list[str] = []
        for item in ordered:
            out = item.output or {}
            if item.tool in {"overview", "missingness"} and isinstance(out.get("columns"), list):
                names.extend(
                    c["column"] for c in out["columns"]
                    if isinstance(c, dict) and isinstance(c.get("column"), str)
                )
            elif item.tool == "describe" and isinstance(out.get("column"), str):
                names.append(out["column"])
        if names:
            lines.extend(_meaning(list(dict.fromkeys(names))))
    for item in ordered:
        out = item.output or {}
        if item.tool == "overview" and _count(out.get("rows")) and _count(out.get("column_count")):
            lines.append(
                f"This table contains {out['rows']:,} rows and {out['column_count']} columns."
            )
            columns = out.get("columns", [])
            if isinstance(columns, list):
                names = [
                    str(c["column"])
                    for c in columns
                    if isinstance(c, dict) and isinstance(c.get("column"), str)
                ]
                if names:
                    lines.append("Columns include: " + ", ".join(names[:10]) + ".")
            if not asks_about_dataset(question):
                lines.append(
                    "Column names describe the recorded measurements; the table alone "
                    "does not identify who collected them or how they were sampled."
                )
        elif item.tool == "missingness" and _count(out.get("rows")):
            if not any(e.tool == "overview" for e in ordered):
                lines.append(f"This table contains {out['rows']:,} rows.")
            columns = out.get("columns", [])
            if isinstance(columns, list):
                valid = [
                    c for c in columns if isinstance(c, dict) and isinstance(c.get("column"), str)
                ]
                if valid:
                    lines.append(
                        "Inspected columns: " + ", ".join(c["column"] for c in valid[:10]) + "."
                    )
                for column in valid:
                    if _count(column.get("missing")) and column["missing"] > 0:
                        lines.append(
                            f"{column['column']} has {column['missing']:,} missing values."
                        )
        elif (
            item.tool == "describe" and isinstance(out.get("column"), str) and _count(out.get("n"))
        ):
            facts = [f"{out['n']:,} recorded values"]
            for key in ("sum", "mean", "median", "min", "max"):
                value = out.get(key)
                if (
                    isinstance(value, int | float)
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                ):
                    facts.append(f"{key} {value:g}")
            lines.append(f"{out['column']}: " + "; ".join(facts) + ".")
        if len(lines) >= 6:
            break
    bounded: list[str] = []
    for line in lines[:6]:
        # Keep complete sentences/numbers: skip a huge column name rather than truncate
        # an identifier or number halfway through it.
        if len("\n".join([*bounded, line])) <= max_chars:
            bounded.append(line)
    return "\n".join(bounded) if bounded else None
