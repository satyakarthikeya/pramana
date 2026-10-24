"""`DataStructure` and `SplitRecord` -- what the gate is told about row dependence (D5, D6).

The gate cannot build a valid null without knowing how the rows depend on each other:
a free shuffle is right for a survey and wrong for monthly figures. The shape is
classified by code in the analysis package and handed over through this contract, so
`verification/` never imports `analysis/`.

Owner: P.P. Satya Karthikeya
Scope: PLAN_analysis_platform.md P1
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pramana.contracts.enums import TableShape

Period = Literal["day", "week", "month", "quarter", "year", "index"]


class DataStructure(BaseModel):
    """How the rows of the table depend on each other.

    Guarantees: any shape other than `cross_section` names its time column and period;
    a panel names its entity column. `declared_by` says who decided the shape, so a
    proof can show whether independence was classified or merely assumed by a caller.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    shape: TableShape
    time_column: str | None = None
    entity_column: str | None = None
    period: Period | None = None
    declared_by: Literal["shape_classifier", "caller"]

    @model_validator(mode="after")
    def _columns_match_shape(self) -> Self:
        if self.shape is TableShape.CROSS_SECTION:
            if self.time_column is not None or self.entity_column is not None:
                raise ValueError("a cross_section has no time or entity column")
            return self
        if not self.time_column or self.period is None:
            raise ValueError(f"a {self.shape.value} table needs a time_column and a period")
        if self.shape is TableShape.PANEL and not self.entity_column:
            raise ValueError("a panel needs an entity_column")
        if self.entity_column is not None and self.entity_column == self.time_column:
            raise ValueError("the entity column cannot also be the time column")
        return self

    @property
    def declared_columns(self) -> tuple[str, ...]:
        """The structural columns a test may read besides the claim's own."""
        return tuple(c for c in (self.time_column, self.entity_column) if c)

    @classmethod
    def independent_rows(cls) -> DataStructure:
        """A caller's explicit statement that rows are independent (free shuffle)."""
        return cls(shape=TableShape.CROSS_SECTION, declared_by="caller")


class SplitRecord(BaseModel):
    """Which rows explored and which rows confirmed (D5), recorded so it can be re-derived.

    Guarantees: the two parts never share a row; `confirmation_digest` hashes the sorted
    positions of the confirmation rows, so a reviewer can check the gate saw the rows
    the split says it did.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Literal["random_rows", "by_time", "by_entity", "none"]
    seed: int
    confirmation_fraction: float = Field(gt=0.0, le=1.0)
    n_exploration: int = Field(ge=0)
    n_confirmation: int = Field(ge=0)
    confirmation_digest: str = Field(min_length=1)
