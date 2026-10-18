"""Provenance screening for the approved NHANES pilot, not proof of unseen training data."""

from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict


class ContaminationScreen(BaseModel):
    """Auditable source decision without making claims about an LLM's training corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    accepted: bool
    notes: list[str]


def screen_source(source: str, urls: list[str]) -> ContaminationScreen:
    """Accept only direct official public NHANES sources for this approved pilot."""
    accepted = source == "NHANES" and bool(urls)
    for url in urls:
        parsed = urlsplit(url)
        accepted = accepted and (
            parsed.scheme == "https"
            and parsed.hostname == "wwwn.cdc.gov"
            and parsed.path.lower().startswith("/nchs/data/nhanes/public/")
            and parsed.path.lower().endswith((".htm", ".xpt"))
            and not parsed.query
            and not parsed.fragment
        )
    return ContaminationScreen(
        accepted=accepted,
        notes=[
            "Direct public-use NHANES component extracts; not Iris, Titanic, Wine, "
            "Boston, mtcars or the packaged diabetes ML benchmark.",
            "No Kaggle/repackaged ML benchmark, MIMIC or PhysioNet source accepted.",
            "NHANES may occur in model training; source screening cannot prove otherwise.",
            "Pilot extracts share participants and are not independent population samples.",
        ]
        if accepted
        else ["Source is outside the approved official NHANES pilot provenance."],
    )
