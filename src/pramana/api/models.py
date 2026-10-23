"""API-owned payloads reuse the authoritative candidate and proof contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pramana.advisory.models import AdvisoryReport
from pramana.analysis.computed import ComputedAnalysis
from pramana.analysis.reader import DataBrief
from pramana.analysis.workspace.ledger import ExplorationSummary
from pramana.contracts import ProofObject, Verdict
from pramana.memory.retrieval import RetrievedLesson
from pramana.orchestration.state import RunStatus


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ColumnPreview(Payload):
    name: str
    role: str
    usable: bool
    reasons: list[str]


class DataPreview(Payload):
    rows: int
    columns: int
    detected_columns: list[ColumnPreview]
    sample_rows: list[dict[str, str]]
    omitted_columns: int = 0


class RunView(Payload):
    run_id: UUID
    dataset_id: UUID | None = None
    status: RunStatus
    file_name: str
    created_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    progress: str = "Queued"
    preview: DataPreview | None = None
    past_lessons: list[RetrievedLesson] = Field(default_factory=list)


class ScatterChart(Payload):
    """Descriptive picture of two numeric columns; never evidence and never gates anything."""

    kind: Literal["scatter"] = "scatter"
    x: str
    y: str
    n: int = Field(ge=0)
    shown: int = Field(ge=0)
    points: list[tuple[float, float]]
    fit: list[tuple[float, float]] = Field(default_factory=list)


class GroupSummary(Payload):
    label: str
    n: int = Field(ge=1)
    minimum: float
    q1: float
    median: float
    q3: float
    maximum: float
    points: list[float]


class GroupsChart(Payload):
    """Descriptive spread of one numeric column across the groups a claim compares."""

    kind: Literal["groups"] = "groups"
    value: str
    group: str
    n: int = Field(ge=0)
    groups: list[GroupSummary]


ChartSpec = Annotated[ScatterChart | GroupsChart, Field(discriminator="kind")]


class Bin(Payload):
    x0: float
    x1: float
    count: int = Field(ge=0)


class CategoryCount(Payload):
    label: str
    count: int = Field(ge=0)


class ColumnOverview(Payload):
    name: str
    kind: Literal["numeric", "category"]
    n: int = Field(ge=0)
    missing: int = Field(ge=0)
    mean: float | None = None
    median: float | None = None
    bins: list[Bin] = Field(default_factory=list)
    top: list[CategoryCount] = Field(default_factory=list)


class CorrelationMatrix(Payload):
    """Descriptive Spearman correlations; untested, so never presented as findings."""

    columns: list[str]
    values: list[list[float | None]]


class DataOverview(Payload):
    rows: int = Field(ge=0)
    columns: list[ColumnOverview]
    correlations: CorrelationMatrix | None = None


class DatasetView(Payload):
    """A stored upload and what code understood about it; no model was involved."""

    dataset_id: UUID
    name: str
    created_at: datetime
    size_bytes: int = Field(ge=0)
    usable_columns: int = Field(ge=0)
    preview: DataPreview
    overview: DataOverview | None = None
    brief: DataBrief | None = None
    #: The Exact tier: arithmetic with its formulas. Shown to the user, never to a model.
    computed: ComputedAnalysis | None = None


class DatasetSummary(Payload):
    dataset_id: UUID
    name: str
    created_at: datetime
    rows: int = Field(ge=0)
    columns: int = Field(ge=0)
    run_count: int = Field(ge=0)
    last_status: RunStatus | None = None


class ResultRow(Payload):
    insight_id: str
    claim: str
    proof: ProofObject
    explanation: str | None = None
    effect_strength: str | None = None
    complete_rows: int | None = Field(default=None, ge=0)
    n_permutations: int | None = Field(default=None, ge=1)
    chart: ChartSpec | None = None


class RunResults(Payload):
    run: RunView
    verified_insights: list[ResultRow]
    rejected_claims: list[ResultRow]
    candidate_count: int = Field(ge=0)
    unverified_candidate_count: int = Field(ge=0)
    exploration: ExplorationSummary | None = None
    #: Advisory summaries and confound caveats for the findings; never part of a verdict.
    advisory: AdvisoryReport | None = None

    @model_validator(mode="after")
    def separate_findings_and_rejections(self) -> RunResults:
        rows = self.verified_insights + self.rejected_claims
        if any(row.proof.verdict is not Verdict.PASS for row in self.verified_insights):
            raise ValueError("a verified finding must have a PASS proof")
        if any(row.proof.verdict is not Verdict.REJECT for row in self.rejected_claims):
            raise ValueError("a rejected claim must have a REJECT proof")
        if any(row.insight_id != row.proof.insight_id for row in rows):
            raise ValueError("result and proof IDs do not match")
        if len({row.insight_id for row in rows}) != len(rows):
            raise ValueError("duplicate result IDs")
        if len(rows) + self.unverified_candidate_count != self.candidate_count:
            raise ValueError("candidate/proof counts do not match")
        return self


class MemorySearch(Payload):
    query: str = Field(min_length=1, max_length=10000)
    top_k: int = Field(default=5, ge=1, le=100)
