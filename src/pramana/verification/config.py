"""Loads `configs/verification.yaml` -- the one place gateway thresholds live.

Why the loader is strict
------------------------
`extra="forbid"` plus no defaults anywhere means a typo'd key (`alpha_typo`) and a
deleted key both fail at load time, loudly, with the offending key named. The
alternative -- pydantic defaults -- fails silently: the gateway keeps running on a
threshold nobody chose, and the run that produced the report is no longer the run the
config describes. Thresholds decide what PASSes; they do not get fallbacks.

Why the whitelist is validated here and not only in the executor
----------------------------------------------------------------
`FORBIDDEN_SANDBOX_IMPORTS` is the check standing between PRAMANA and its own central
claim. If a statistics library is importable inside generated code, that code can
compute its own p-value and the gate ends up reading a number nobody audited. Refusing
such a config at LOAD time means the dangerous configuration cannot exist at runtime,
rather than being caught (or not) by whoever reviews the YAML.

The line the whitelist draws is between LIBRARIES and OUR library:
`pramana.verification.stats` imports scipy internally and is allowed, because it is
audited code covered by known-answer tests. Generated code importing scipy directly is
not. A blunter rule ("nothing that touches scipy") would ban the gateway's own stats
module and break the gate entirely.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 2 component 8
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pramana.contracts.enums import EffectMetric

#: Repository root, resolved from this file: verification -> pramana -> src -> root.
_REPO_ROOT = Path(__file__).resolve().parents[3]

#: The config the gateway runs on unless a caller passes another path.
DEFAULT_CONFIG_PATH = _REPO_ROOT / "configs" / "verification.yaml"

#: Root packages generated code may never import. Each one can produce a p-value, an
#: effect size or a model fit on its own, which is exactly the capability the gate
#: exists to deny untrusted code (PROJECT.md 3, AGENTS.md 3.1).
FORBIDDEN_SANDBOX_IMPORTS: frozenset[str] = frozenset(
    {
        "scipy",
        "statsmodels",
        "sklearn",
        "pingouin",
        "lifelines",
        "pymc",
        "arviz",
        "researchpy",
    }
)


class StatisticsConfig(BaseModel):
    """Resampling parameters and the FDR level. No field has a default."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    alpha: float = Field(gt=0.0, lt=1.0, description="BH-FDR level, applied across the run.")
    n_permutations: int = Field(ge=1000, description="Resamples per permutation test.")
    n_bootstrap: int = Field(ge=1000, description="Resamples per bootstrap interval.")
    seed: int = Field(description="Configurable AND logged, for reproducibility (AGENTS.md 3.4).")
    min_observations: int = Field(
        ge=2,
        description="Usable rows below which a test concludes nothing and fails closed, "
        "rather than reporting a p-value computed from a handful of points.",
    )


class EffectBand(BaseModel):
    """The gating band for one effect metric.

    `min` is the floor below which an effect is NEGLIGIBLE however small its q-value
    is (AGENTS.md 3.5). `strong` is where the effect leg of the evidence score
    saturates -- a reference point for ranking, never for the verdict.

    Bands are per metric because the metrics are not on a common scale: Kendall's
    tau-b runs systematically smaller than Spearman's rho for the same relationship,
    so one global cutoff would quietly make trend claims harder to pass than
    correlation claims.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    min: float = Field(gt=0.0, description="Floor for a non-negligible effect.")
    strong: float = Field(gt=0.0, description="Where the effect leg reaches 1.0.")

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.min < self.strong:
            raise ValueError(f"effect band needs min < strong; got min={self.min}, strong={self.strong}")
        return self


class EvidenceConfig(BaseModel):
    """Per-metric gating bands. Every `EffectMetric` must appear."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    effect_thresholds: dict[EffectMetric, EffectBand]

    @model_validator(mode="after")
    def _every_metric_is_banded(self) -> Self:
        """Guarantees: `threshold_for` never raises a KeyError at verdict time.

        A metric with no band would surface as a crash in the middle of a run, after
        the expensive part; catching it at load time costs nothing.
        """
        missing = sorted(set(EffectMetric) - set(self.effect_thresholds))
        if missing:
            raise ValueError(f"effect_thresholds is missing a band for {missing}")
        return self

    def threshold_for(self, metric: EffectMetric) -> EffectBand:
        """The band `metric` is gated on."""
        return self.effect_thresholds[metric]


class ExecutorConfig(BaseModel):
    """Sandbox limits and the import whitelist (AGENTS.md 4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timeout_seconds: int = Field(gt=0, description="After this, the test failed. Never a PASS.")
    max_memory_mb: int = Field(gt=0)
    max_retries: int = Field(ge=0, description="Exhausted retries fail closed.")
    allowed_imports: list[str] = Field(
        min_length=1, description="The only modules generated code may import."
    )

    @model_validator(mode="after")
    def _no_statistics_library_is_whitelisted(self) -> Self:
        """Guarantees: no entry resolves to a forbidden root package.

        Matching on the root closes the obvious dodge -- `scipy.stats` is scipy, and
        whitelisting the submodule would whitelist the capability.
        """
        offending = sorted(
            {
                name
                for name in self.allowed_imports
                if name.split(".")[0] in FORBIDDEN_SANDBOX_IMPORTS
            }
        )
        if offending:
            raise ValueError(
                f"allowed_imports must not contain a statistics library: {offending}. "
                f"Generated code that can compute its own p-value defeats the gate "
                f"(PROJECT.md 3); call pramana.verification.stats instead."
            )
        return self


class LLMConfig(BaseModel):
    """Which falsification generator runs, and the model behind the optional one.

    The default is `template`: deterministic, no API key, no network, so the gateway
    runs offline and its output is byte-reproducible. The `llm` path is the secondary
    generator measured against it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    generator: Literal["template", "llm"]
    provider: str
    model: str
    temperature: float = Field(ge=0.0, le=2.0)


class VerificationConfig(BaseModel):
    """Everything the gateway is allowed to be configured with."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    statistics: StatisticsConfig
    evidence: EvidenceConfig
    executor: ExecutorConfig
    llm: LLMConfig

    @property
    def p_value_floor(self) -> float:
        """The smallest p-value a permutation test can report: `1 / (B + 1)`.

        Derived rather than configured, because it is not a tunable threshold -- it is
        a property of add-one ("plus-one") estimation with `n_permutations` resamples,
        and a configured value could silently disagree with the test that produced the
        p-value. The significance leg of the evidence score uses it as its saturation
        point, so it must be below alpha for that leg to be defined at all.
        """
        return 1.0 / (self.statistics.n_permutations + 1)


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> VerificationConfig:
    """Load and validate the verification config.

    Guarantees: every value the gateway uses came from `path`. A missing key, an
    unknown key, an out-of-range value or a statistics library in the sandbox
    whitelist raises `ValidationError` here, before any claim is tested.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return VerificationConfig.model_validate(raw)
