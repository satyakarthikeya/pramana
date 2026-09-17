"""Loads `configs/analysis.yaml` -- the one place this module's tunables live.

Why a loader rather than inline constants
-----------------------------------------
`AGENTS.md` 3.3 is written about the gateway's thresholds, but the reasoning carries:
a number that decides whether a column is usable, or whether a pair is worth
proposing, changes what the gateway is asked to test. If it lives in a function
signature, the run that produced the report is no longer the run the config
describes. Every heuristic cutoff in this module is read from here.

Why only two sections are modelled strictly
-------------------------------------------
`configs/analysis.yaml` also carries `ingestion`, `cleaning` and `benchmark` sections
belonging to components this loader does not serve. The top-level model therefore
IGNORES unknown sections, so those can evolve without touching this code, while the
two sections consumed here are `extra="forbid"` with no defaults: a typo'd or deleted
key inside them fails at load, loudly, rather than quietly substituting a cutoff
nobody chose.

Owner: P. Rohith (built by P.P. Satya Karthikeya -- team-agreed cross-module work)
Scope: scope/SCOPE_P_Rohith.md 2, components 2 and 4
"""

from __future__ import annotations

from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Repository root, resolved from this file: analysis -> pramana -> src -> root.
_REPO_ROOT = Path(__file__).resolve().parents[3]

#: The config this module runs on unless a caller passes another path.
DEFAULT_CONFIG_PATH = _REPO_ROOT / "configs" / "analysis.yaml"

#: Model families reserved for the verification gateway (`AGENTS.md` 2). Routing
#: schema inference through one of them is a cost and scope violation, not a style
#: choice, so the configuration that would do it is refused at load time rather than
#: caught in review. Matched on the leading token, because "deepseek-v4" is DeepSeek.
VERIFICATION_TIER_MODELS: frozenset[str] = frozenset(
    {"deepseek", "deepseek-v4", "deepseek-chat", "deepseek-reasoner"}
)


class SchemaInferenceConfig(BaseModel):
    """Cutoffs for deterministic column classification (SCOPE_P 2, component 2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    use_llm_for_ambiguous_only: bool = Field(
        description="Heuristics decide first; the semantic refiner only ever sees what they "
        "could not classify confidently."
    )
    model: str = Field(
        min_length=1,
        description="The local sub-agent model for cheap semantic work. Gemma-tier only.",
    )
    min_confidence: float = Field(
        gt=0.0,
        le=1.0,
        description="Below this a column is UNKNOWN and unusable for hypotheses, rather than "
        "carrying a guessed role downstream.",
    )
    min_non_null: int = Field(
        ge=1, description="Usable rows below which a column cannot be classified at all."
    )
    id_unique_ratio: float = Field(
        gt=0.0,
        le=1.0,
        description="Distinct-value share at or above which a column is identifier-like.",
    )
    categorical_max_levels: int = Field(
        ge=2,
        description="More distinct levels than this and a labelled column is not a grouping.",
    )
    ordinal_max_levels: int = Field(
        ge=2, description="Integer columns with at most this many levels read as ordinal."
    )
    datetime_parse_min_ratio: float = Field(
        gt=0.0,
        le=1.0,
        description="Share of non-null values that must parse as timestamps before a text "
        "column is called datetime.",
    )

    @model_validator(mode="after")
    def _model_is_not_verification_tier(self) -> Self:
        """Guarantees: the configured model is not the gateway's (`AGENTS.md` 2).

        Schema inference is explicitly routine sub-agent work. Refusing the
        configuration means the expensive, trust-critical model cannot be spent on it
        by accident, and the rule is enforced by the loader rather than by whoever
        reviews the YAML.
        """
        if self.model.strip().casefold().split("/")[-1] in VERIFICATION_TIER_MODELS:
            raise ValueError(
                f"schema_inference.model {self.model!r} is a verification-tier model; "
                f"schema inference is routine sub-agent work and runs on the local model "
                f"(AGENTS.md 2). Verification-tier models: {sorted(VERIFICATION_TIER_MODELS)}"
            )
        return self

    @model_validator(mode="after")
    def _ordinal_fits_inside_categorical(self) -> Self:
        """Guarantees: the two level caps cannot disagree about the same column.

        An ordinal cap above the categorical cap would call a 30-level integer column
        ordinal while calling the same 30 labels too many to be a grouping -- the
        order of the checks, not the data, would decide the role.
        """
        if self.ordinal_max_levels > self.categorical_max_levels:
            raise ValueError(
                f"ordinal_max_levels ({self.ordinal_max_levels}) must not exceed "
                f"categorical_max_levels ({self.categorical_max_levels})"
            )
        return self


class StrategyToggles(BaseModel):
    """Which hypothesis strategies run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation: bool
    group_difference: bool
    trend: bool


class HypothesesConfig(BaseModel):
    """Caps and exploratory pre-filters for candidate generation (SCOPE_P 2, component 4).

    Every threshold here is a PRE-FILTER on what is worth proposing, and none of them
    is a verdict: a pair that clears `min_abs_correlation` has been proposed, not
    verified. The module is the proposer; the gateway is the judge.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_candidates_per_run: int = Field(
        ge=1, description="Hard cap on the batch handed to the gateway, so BH-FDR stays sane."
    )
    strategies: StrategyToggles
    min_abs_correlation: float = Field(
        ge=0.0, le=1.0, description="Exploratory |rho| floor for a correlation candidate."
    )
    min_observations: int = Field(
        ge=2,
        description="Pairwise-complete rows below which no candidate is proposed at all. "
        "Mirrors the gateway's own floor: a claim the gateway could only ever call "
        "INCONCLUSIVE should not consume a slot in the BH family.",
    )
    min_group_size: int = Field(
        ge=2, description="Rows a level needs before it counts as a comparable group."
    )
    min_group_levels: int = Field(ge=2, description="Fewest levels a grouping column may have.")
    max_group_levels: int = Field(
        ge=2, description="Most levels a grouping column may have before it stops being one."
    )
    min_group_effect: float = Field(
        ge=0.0,
        le=1.0,
        description="Exploratory eta-squared floor for a group-difference candidate.",
    )
    min_abs_trend_tau: float = Field(
        ge=0.0, le=1.0, description="Exploratory |tau-b| floor for a trend candidate."
    )

    @model_validator(mode="after")
    def _group_levels_are_ordered(self) -> Self:
        if self.min_group_levels > self.max_group_levels:
            raise ValueError(
                f"min_group_levels ({self.min_group_levels}) must not exceed "
                f"max_group_levels ({self.max_group_levels})"
            )
        return self


class AnalysisConfig(BaseModel):
    """The slice of `configs/analysis.yaml` this module's two components read.

    Unknown top-level sections are ignored on purpose -- `ingestion`, `cleaning` and
    `benchmark` belong to components served elsewhere, and this loader has no business
    failing when they change.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    schema_inference: SchemaInferenceConfig
    hypotheses: HypothesesConfig


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> AnalysisConfig:
    """Load and validate the analysis config.

    Guarantees: every cutoff used by schema inference and candidate generation came
    from `path`. A missing key, an unknown key inside a served section, an
    out-of-range value, or a verification-tier model raises `ValidationError` here --
    before a single column is classified.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return AnalysisConfig.model_validate(raw)
