"""Sector packs: data-only YAML that tells the core analyses what the columns mean.

A pack (`configs/sectors/<name>.yaml`) maps column-name tokens to semantic roles, names
the additive measures and known identities, and lists which core analyses run. It holds
no code, so adding a sector cannot add unreviewed logic (PLAN §14). A new analysis TYPE
is core code; a new SECTOR only selects and parameterises existing types.

Detection is deterministic: count how many distinct roles a pack recognises in the
column names, pick the best pack if it clears `MIN_ROLES_FOR_SECTOR`, else `general`.
The user can override the choice. No model is consulted.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.config import DEFAULT_CONFIG_PATH

SECTOR_DIR = DEFAULT_CONFIG_PATH.parent / "sectors"

#: Distinct non-entity roles a pack must recognise before a table is called that
#: sector. One matching word ("sales") is too weak; two independent ones are not.
MIN_ROLES_FOR_SECTOR = 2

#: Roles that describe WHO or WHERE rather than WHAT is measured; they do not count
#: towards detection because nearly every table has a region or a category.
_CONTEXT_ROLES = frozenset({"entity"})


class Identity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    result: str
    op: Literal["difference", "sum", "ratio", "product", "bmi"]
    inputs: list[str] = Field(min_length=2, max_length=2)


class PrevalenceRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: str
    label: str
    op: Literal[">=", ">", "<=", "<", "=="]
    value: float
    unit: str | None = None


class Wording(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scope_note: str = ""
    refusal: str = ""


class SectorPack(BaseModel):
    """One sector's vocabulary and analysis selection. Guarantees: data only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    description: str = ""
    roles: dict[str, list[str]] = Field(default_factory=dict)
    codebook_roles: dict[str, str] = Field(default_factory=dict)
    measures: list[str] = Field(default_factory=list)
    additive_measures: bool = Field(
        default=True,
        description="Whether measures can be summed (revenue can; BMI cannot). Totals, "
        "shares and period changes run only on additive measures; others are averaged.",
    )
    nonnegative: list[str] = Field(default_factory=list)
    identities: list[Identity] = Field(default_factory=list)
    prevalence: list[PrevalenceRule] = Field(default_factory=list)
    breakdowns: list[str] = Field(default_factory=list)
    age_bands: list[float] = Field(default_factory=list)
    analyses: list[str] = Field(min_length=1)
    wording: Wording = Field(default_factory=Wording)


#: The fallback when no pack fits: generic analyses on whatever numeric and grouping
#: columns the schema found. Built in code because it IS the core's default behaviour.
GENERAL = SectorPack(
    name="general",
    label="General",
    description="No sector vocabulary matched; generic analyses only.",
    analyses=[
        "period_change",
        "variance_decomposition",
        "concentration",
        "segment_ranking",
        "outliers",
        "seasonality",
        "data_quality",
    ],
    wording=Wording(scope_note="Figures are computed from this table only."),
)


class SectorMatch(BaseModel):
    """Which pack a table was read with, and which column got which role."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sector: str
    label: str
    score: int = Field(ge=0)
    roles: dict[str, str] = Field(default_factory=dict)
    reasons: list[str] = Field(min_length=1)


def load_packs(directory: Path = SECTOR_DIR) -> dict[str, SectorPack]:
    """Every pack in `directory`, keyed by name. Raises on an invalid pack."""
    packs: dict[str, SectorPack] = {}
    for path in sorted(directory.glob("*.yaml")):
        pack = SectorPack.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if pack.name in packs or pack.name == GENERAL.name:
            raise ValueError(f"duplicate sector pack name {pack.name!r} in {path.name}")
        packs[pack.name] = pack
    return packs


def name_tokens(column: str) -> list[str]:
    """Lower-case word tokens of a column name: snake, kebab, spaces and camelCase."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", column)
    return [t for t in re.split(r"[^0-9A-Za-z]+", spaced.lower()) if t]


def roles_for(columns: Sequence[str], pack: SectorPack) -> dict[str, str]:
    """Column -> role under `pack`. Codebook names win, then the whole name, then tokens.

    Labels and codings for codebook columns stay in `analysis/codebook.py`; the pack
    only says which role such a column plays.
    """
    vocabulary = {token: role for role, tokens in pack.roles.items() for token in tokens}
    found: dict[str, str] = {}
    for column in columns:
        key = column.strip().upper()
        if key in pack.codebook_roles:
            found[column] = pack.codebook_roles[key]
            continue
        tokens = name_tokens(column)
        joined = "".join(tokens)
        role = vocabulary.get(joined) or next(
            (vocabulary[t] for t in tokens if t in vocabulary), None
        )
        if role is not None:
            found[column] = role
    return found


def _score(roles: Mapping[str, str]) -> int:
    return len({role for role in roles.values() if role not in _CONTEXT_ROLES})


def detect_sector(
    columns: Sequence[str],
    packs: Mapping[str, SectorPack],
    override: str | None = None,
) -> SectorMatch:
    """Pick the pack that recognises the most distinct roles, or `general`.

    Guarantees: deterministic for the same columns and packs; ties fall back to
    `general` rather than to file order; an override that names no pack raises.
    """
    if override is not None:
        if override == GENERAL.name:
            return SectorMatch(
                sector="general",
                label=GENERAL.label,
                score=0,
                reasons=["general chosen by override"],
            )
        if override not in packs:
            raise ValueError(f"unknown sector {override!r}; known: {sorted(packs)}")
        pack = packs[override]
        roles = roles_for(columns, pack)
        return SectorMatch(
            sector=pack.name,
            label=pack.label,
            score=_score(roles),
            roles=roles,
            reasons=[f"{pack.label} chosen by override"],
        )

    scored = sorted(
        ((_score(roles_for(columns, p)), name) for name, p in packs.items()), reverse=True
    )
    if not scored or scored[0][0] < MIN_ROLES_FOR_SECTOR:
        best = scored[0][0] if scored else 0
        return SectorMatch(
            sector="general",
            label=GENERAL.label,
            score=best,
            reasons=[f"no sector recognised {MIN_ROLES_FOR_SECTOR} or more column meanings"],
        )
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return SectorMatch(
            sector="general",
            label=GENERAL.label,
            score=scored[0][0],
            reasons=[f"{scored[0][1]} and {scored[1][1]} matched equally well"],
        )
    pack = packs[scored[0][1]]
    roles = roles_for(columns, pack)
    named = ", ".join(f"{column} as {role}" for column, role in roles.items())
    return SectorMatch(
        sector=pack.name,
        label=pack.label,
        score=scored[0][0],
        roles=roles,
        reasons=[f"recognised {named}"],
    )


def pack_for(match: SectorMatch, packs: Mapping[str, SectorPack]) -> SectorPack:
    return packs.get(match.sector, GENERAL)
