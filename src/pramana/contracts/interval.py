"""`EffectInterval` -- how precisely the tested rows pin down the effect (design v3, S5).

A permutation test says whether chance could have produced the effect; the interval says
how far the effect itself could move on a repeat. It is shown beside the effect and never
enters the verdict (decision 2: the band rule is unchanged).

Owner: P.P. Satya Karthikeya
Scope: docs/DESIGN_verification_gateway_v3.md S5
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EffectInterval(BaseModel):
    """A percentile bootstrap interval on the gated effect.

    Guarantees: `low <= estimate <= high` is NOT promised (a percentile interval can miss
    the point estimate when the statistic is biased); `low <= high` is. `method` says what
    was resampled, so the dependence in the rows is respected: whole entities for a
    cluster or paired null, whole periods for a within-period null, rows otherwise.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    estimate: float
    low: float
    high: float
    confidence: float = Field(gt=0.0, lt=1.0)
    method: Literal["row_bootstrap", "entity_bootstrap", "period_bootstrap"]
    n_resamples: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> EffectInterval:
        if self.low > self.high:
            raise ValueError("low must not exceed high")
        return self
