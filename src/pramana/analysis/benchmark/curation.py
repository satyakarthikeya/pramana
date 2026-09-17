"""Manifest-based curation of the 40-dataset evaluation benchmark."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .contamination import ContaminationResult, screen_source


class DatasetRecord(BaseModel):
    """One reproducible source entry; raw data remains outside Git."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    local_path: str | None = None
    source_family: str = Field(min_length=1)
    seed: int
    contamination: ContaminationResult


class BenchmarkManifest(BaseModel):
    """Validated benchmark inventory and its screening decisions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required_count: int = 40
    datasets: list[DatasetRecord]

    def validate_ready(self) -> None:
        """Fail unless the manifest is exactly the planned benchmark size and clean."""

        if len(self.datasets) != self.required_count:
            raise ValueError(
                f"benchmark requires {self.required_count} datasets, got {len(self.datasets)}"
            )
        ids = [dataset.dataset_id for dataset in self.datasets]
        if len(set(ids)) != len(ids):
            raise ValueError("benchmark dataset_id values must be unique")
        rejected = [dataset.dataset_id for dataset in self.datasets if not dataset.contamination.accepted]
        if rejected:
            raise ValueError(f"benchmark contains rejected sources: {rejected}")


def curate_manifest(
    sources: Iterable[dict[str, object]],
    *,
    required_count: int = 40,
) -> BenchmarkManifest:
    """Screen source metadata and build a manifest without downloading raw data."""

    records: list[DatasetRecord] = []
    for source in sources:
        dataset_id = str(source["dataset_id"])
        name = str(source["name"])
        origin = str(source["source"])
        tags = {str(tag) for tag in source.get("tags", [])}  # type: ignore[union-attr]
        contamination = screen_source(
            dataset_id=dataset_id,
            name=name,
            source=origin,
            tags=tags,
        )
        records.append(
            DatasetRecord(
                dataset_id=dataset_id,
                name=name,
                source=origin,
                source_url=str(source["source_url"]),
                local_path=str(source["local_path"]) if source.get("local_path") else None,
                source_family=str(source["source_family"]),
                seed=int(source.get("seed", 20260817)),
                contamination=contamination,
            )
        )
    manifest = BenchmarkManifest(required_count=required_count, datasets=records)
    manifest.validate_ready()
    return manifest


def validate_local_files(manifest: BenchmarkManifest) -> list[Path]:
    """Return available local files and fail clearly for missing benchmark inputs."""

    missing = [
        dataset.dataset_id
        for dataset in manifest.datasets
        if dataset.local_path and not Path(dataset.local_path).is_file()
    ]
    if missing:
        raise FileNotFoundError(f"missing local benchmark files: {missing}")
    return [Path(dataset.local_path) for dataset in manifest.datasets if dataset.local_path]
