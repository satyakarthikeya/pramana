"""`PowerNote` -- how small an effect the tested rows could have detected (design v3, S1).

A REJECT because the evidence was not strong enough is not a statement that the claim
is false. The note says how large an effect would have had to be for the test to find
it reasonably often, so a reader can tell "no effect" from "too little data". It is
descriptive: it never enters the verdict, the family or memory.

Owner: P.P. Satya Karthikeya
Scope: docs/DESIGN_verification_gateway_v3.md S1
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pramana.contracts.enums import EffectMetric


class PowerNote(BaseModel):
    """The smallest effect detectable with `target_power` at level `alpha`.

    Guarantees: computed from the sample size the test actually had (`n_effective`, in
    `unit`), before the multiple-testing correction, so it is a lower bound on what a
    corrected test needed; an approximation from a normal or noncentral-F model, not a
    simulation of the gate.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    effect_metric: EffectMetric
    detectable_effect: float = Field(gt=0.0)
    n_effective: int = Field(ge=1)
    unit: Literal["observations", "periods", "entities", "origin_blocks"]
    alpha: float = Field(gt=0.0, lt=1.0)
    target_power: float = Field(gt=0.0, lt=1.0)
