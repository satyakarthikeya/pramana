"""Contamination screening for benchmark source datasets."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


FAMOUS_DATASETS = frozenset(
    {"iris", "titanic", "mtcars", "boston", "wine", "diabetes", "mnist"}
)
FORBIDDEN_SOURCES = frozenset({"mimic-iv", "mimic", "physionet"})


class ContaminationResult(BaseModel):
    """Auditable result of screening one proposed source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    matched_rules: list[str]
    reason: str


def screen_source(
    *,
    dataset_id: str,
    name: str,
    source: str,
    tags: set[str] | frozenset[str] = frozenset(),
) -> ContaminationResult:
    """Reject famous or forbidden sources before they enter the benchmark."""

    values = {
        "dataset_id": dataset_id.casefold(),
        "name": name.casefold(),
        "source": source.casefold(),
        "tags": " ".join(sorted(tag.casefold() for tag in tags)),
    }
    haystack = " ".join(values.values())
    matched: list[str] = []
    for item in sorted(FAMOUS_DATASETS):
        if item in haystack:
            matched.append(f"famous_dataset:{item}")
    for item in sorted(FORBIDDEN_SOURCES):
        if item in haystack:
            matched.append(f"forbidden_source:{item}")
    if matched:
        return ContaminationResult(
            accepted=False,
            matched_rules=matched,
            reason="; ".join(matched),
        )
    return ContaminationResult(
        accepted=True,
        matched_rules=[],
        reason="no excluded dataset or forbidden source matched",
    )
