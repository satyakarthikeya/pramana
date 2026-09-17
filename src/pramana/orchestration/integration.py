"""Validated plug-in boundary for teammate-owned workflow implementations.

Teammate packages expose plain ``request mapping -> response mapping`` handlers and do
not import orchestration. This module owns translating those mappings into graph state,
so public analysis or memory implementations can land without changing the graph.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pramana.common.config import RuntimeConfig
from pramana.contracts import CandidateInsight, ProofObject, Verdict
from pramana.orchestration.adapters import (
    IntegrationDependencyError,
    StateAdapter,
    WorkflowAdapters,
    celery_verification_adapter,
    safe_report_adapter,
)
from pramana.orchestration.state import PramanaState

Handler = Callable[[Mapping[str, Any]], Mapping[str, Any]]
IntegrationModelT = TypeVar("IntegrationModelT", bound="_IntegrationModel")

INGEST_HANDLER_ENV = "PRAMANA_INGEST_HANDLER"
PREPARATION_HANDLER_ENV = "PRAMANA_PREPARATION_HANDLER"
ANALYSIS_HANDLER_ENV = "PRAMANA_ANALYSIS_HANDLER"
MEMORY_HANDLER_ENV = "PRAMANA_MEMORY_HANDLER"


class _IntegrationModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)


class IngestRequest(_IntegrationModel):
    """Input supplied to the analysis-owned dataset loader."""

    run_id: UUID
    dataset_ref: str = Field(min_length=1)


class IngestResult(_IntegrationModel):
    """Loaded dataset plus the stable reference representing those exact values."""

    dataset: Any
    dataset_ref: str = Field(min_length=1)

    @field_validator("dataset")
    @classmethod
    def dataset_is_present(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("ingestion must return a dataset")
        return value


class PreparationRequest(_IntegrationModel):
    """Input supplied to analysis-owned cleaning, profiling, and schema inference."""

    run_id: UUID
    dataset: Any
    dataset_ref: str = Field(min_length=1)

    @field_validator("dataset")
    @classmethod
    def dataset_is_present(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("preparation requires the ingested dataset")
        return value


class PreparationResult(_IntegrationModel):
    """Cleaned data, its shared worker-visible reference, and its schema profile."""

    dataset: Any
    dataset_ref: str = Field(min_length=1)
    schema_profile: dict[str, Any]

    @field_validator("dataset")
    @classmethod
    def dataset_is_present(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("preparation must return the cleaned dataset")
        return value


class AnalysisRequest(_IntegrationModel):
    """Cleaned dataset and profile supplied to candidate generation."""

    run_id: UUID
    dataset: Any
    dataset_ref: str = Field(min_length=1)
    schema_profile: dict[str, Any]
    user_query: str | None = None

    @field_validator("dataset")
    @classmethod
    def dataset_is_present(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("analysis requires the cleaned dataset")
        return value


class AnalysisResult(_IntegrationModel):
    """Unique contract-valid candidates emitted as proposals, never verdicts."""

    candidate_insights: list[CandidateInsight]

    @model_validator(mode="after")
    def unique_insight_ids(self) -> AnalysisResult:
        identifiers = [candidate.insight_id for candidate in self.candidate_insights]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("candidate insight IDs must be unique within a run")
        return self


class MemoryWriteRequest(_IntegrationModel):
    """The only payload passed to memory: gateway-issued PASS proofs and run context."""

    run_id: UUID
    dataset_ref: str | None
    proof_objects: list[ProofObject]

    @model_validator(mode="after")
    def only_pass_proofs(self) -> MemoryWriteRequest:
        rejected = [
            proof.insight_id for proof in self.proof_objects if proof.verdict is not Verdict.PASS
        ]
        if rejected:
            raise ValueError(f"memory request contains non-PASS proofs: {rejected}")
        return self


class MemoryWriteResult(_IntegrationModel):
    """Opaque storage receipts retained in graph state for audit and API use."""

    memory_receipts: list[Any]


def load_handler(env_name: str, package: str) -> Handler:
    """Load one public handler from its package-scoped environment setting."""
    import_path = os.getenv(env_name, "").strip()
    if not import_path:
        raise IntegrationDependencyError(f"{env_name} is not configured")
    module_name, separator, attribute = import_path.partition(":")
    in_package = module_name == package or module_name.startswith(f"{package}.")
    if not separator or not in_package or not attribute.isidentifier() or attribute.startswith("_"):
        raise IntegrationDependencyError(
            f"{env_name} must use {package}[.<module>]:<public_function>"
        )
    try:
        candidate = getattr(importlib.import_module(module_name), attribute)
    except (AttributeError, ImportError) as error:
        raise IntegrationDependencyError(
            f"Cannot load configured handler {import_path!r}"
        ) from error
    if not callable(candidate):
        raise IntegrationDependencyError(f"Configured handler is not callable: {import_path}")
    return cast(Handler, candidate)


def _request(model: _IntegrationModel) -> dict[str, Any]:
    return model.model_dump(mode="python")


def _response(
    handler: Handler,
    request: _IntegrationModel,
    model: type[IntegrationModelT],
) -> IntegrationModelT:
    response = handler(_request(request))
    if not isinstance(response, Mapping):
        raise ValueError(f"{type(request).__name__} handler returned a non-mapping response")
    return model.model_validate(response)


def configured_adapters(*, verify: StateAdapter = celery_verification_adapter) -> WorkflowAdapters:
    """Build production adapters from configured, package-restricted public handlers."""
    ingest_handler = load_handler(INGEST_HANDLER_ENV, "pramana.analysis")
    preparation_handler = load_handler(PREPARATION_HANDLER_ENV, "pramana.analysis")
    analysis_handler = load_handler(ANALYSIS_HANDLER_ENV, "pramana.analysis")
    memory_handler = load_handler(MEMORY_HANDLER_ENV, "pramana.memory")

    def ingest(state: PramanaState) -> Mapping[str, Any]:
        if not state.dataset_ref:
            raise ValueError("dataset_ref is required before ingestion")
        result = _response(
            ingest_handler,
            IngestRequest(run_id=state.run_id, dataset_ref=state.dataset_ref),
            IngestResult,
        )
        return result.model_dump(mode="python")

    def prepare(state: PramanaState) -> Mapping[str, Any]:
        if not state.dataset_ref:
            raise ValueError("dataset_ref is required before preparation")
        result = _response(
            preparation_handler,
            PreparationRequest(
                run_id=state.run_id,
                dataset=state.dataset,
                dataset_ref=state.dataset_ref,
            ),
            PreparationResult,
        )
        return result.model_dump(mode="python")

    def analyze(state: PramanaState) -> Mapping[str, Any]:
        if not state.dataset_ref:
            raise ValueError("cleaned dataset_ref is required before candidate generation")
        result = _response(
            analysis_handler,
            AnalysisRequest(
                run_id=state.run_id,
                dataset=state.dataset,
                dataset_ref=state.dataset_ref,
                schema_profile=state.schema_profile,
                user_query=state.user_query,
            ),
            AnalysisResult,
        )
        mismatched = [
            candidate.insight_id
            for candidate in result.candidate_insights
            if candidate.dataset_ref != state.dataset_ref
        ]
        if mismatched:
            raise ValueError(
                "Candidates must reference the exact cleaned dataset; "
                f"mismatched insight IDs: {mismatched}"
            )
        return result.model_dump(mode="python")

    def memory_write(state: PramanaState, proofs: Sequence[ProofObject]) -> Mapping[str, Any]:
        result = _response(
            memory_handler,
            MemoryWriteRequest(
                run_id=state.run_id,
                dataset_ref=state.dataset_ref,
                proof_objects=list(proofs),
            ),
            MemoryWriteResult,
        )
        return result.model_dump(mode="python")

    return WorkflowAdapters(
        ingest=ingest,
        subagents=prepare,
        analyze=analyze,
        verify=verify,
        memory_write=memory_write,
        report=safe_report_adapter,
    )


def run_configured_workflow(
    dataset_ref: str,
    *,
    user_query: str | None = None,
    runtime: RuntimeConfig | None = None,
) -> PramanaState:
    """Run the production graph through configured teammate entrypoints."""
    from pramana.orchestration.graph import build_graph, run_graph
    from pramana.orchestration.run_lifecycle import new_run

    state = new_run(dataset_ref, runtime=runtime, user_query=user_query)
    return run_graph(state, build_graph(configured_adapters()))
