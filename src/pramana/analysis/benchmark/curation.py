"""Reproducible, unshuffled NHANES extracts and Satya's metadata handoff."""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pramana.analysis.benchmark.contamination import ContaminationScreen, screen_source
from pramana.analysis.config import load_config
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile, infer_schema

Role = Literal["numeric", "categorical", "ordinal", "datetime", "id"]
ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PLAN = ROOT / "configs" / "benchmark_pilot.yaml"
BASE_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/{year}/DataFiles/{component}"


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Cycle(StrictModel):
    year: int
    label: str


class ExtractSpec(StrictModel):
    dataset_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    cycles: list[Literal["H", "I", "J"]] = Field(min_length=1)
    modules: list[str] = Field(min_length=1)
    rows_per_cycle: int = Field(ge=300, le=5000)
    coverage: Literal["numeric_pairs", "group_differences", "trends", "mixed"]
    columns: dict[str, Role]
    time_column: str | None = None

    @model_validator(mode="after")
    def valid_components(self) -> Self:
        if any(not re.fullmatch(r"[A-Z]+", name) or name == "DEMO" for name in self.modules):
            raise ValueError(
                "modules must be distinct uppercase NHANES module names, excluding DEMO"
            )
        if len(set(self.modules)) != len(self.modules) or len(set(self.cycles)) != len(self.cycles):
            raise ValueError("modules and cycles must be unique")
        if len(self.cycles) * self.rows_per_cycle > 5000:
            raise ValueError("an extract cannot exceed 5000 rows")
        if self.coverage == "trends" and (len(self.cycles) < 2 or self.time_column != "SDDSRVYR"):
            raise ValueError(
                "trend extracts require multiple cycles and the original SDDSRVYR axis"
            )
        return self


class PilotPlan(StrictModel):
    phase: Literal["pilot"]
    required_count: Literal[10]
    seed: int = Field(ge=0)
    min_age: int = Field(ge=20)
    download_timeout_seconds: int = Field(gt=0)
    common_columns: dict[str, Role]
    weight_columns: list[str]
    id_columns: list[str]
    design_columns: list[str]
    cycles: dict[str, Cycle]
    extracts: list[ExtractSpec]

    @model_validator(mode="after")
    def valid_pilot(self) -> Self:
        ids = [item.dataset_id for item in self.extracts]
        if len(ids) != self.required_count or len(set(ids)) != len(ids):
            raise ValueError("pilot count or unique dataset IDs do not match")
        for kind in ("numeric_pairs", "group_differences", "trends"):
            if sum(item.coverage == kind for item in self.extracts) < 3:
                raise ValueError(f"pilot requires at least three extracts covering {kind}")
        for spec in self.extracts:
            if not 8 <= len(self.common_columns | spec.columns) <= 30:
                raise ValueError("extracts require 8 to 30 columns")
            if set(spec.columns) & set(self.common_columns):
                raise ValueError("module columns must not redefine common columns")
            if not set(spec.cycles) <= set(self.cycles):
                raise ValueError("unknown survey cycle")
        if not set(self.id_columns + self.weight_columns + self.design_columns) <= set(
            self.common_columns
        ):
            raise ValueError("all ID, weight and design columns must be present")
        return self


class SourceRecord(StrictModel):
    component: str
    cycle: str
    data_url: str
    codebook_url: str
    data_sha256: str
    codebook_sha256: str


class ColumnMetadata(StrictModel):
    dtype: Role
    missing_pct: float = Field(ge=0, le=100)
    missing_count: int = Field(ge=0)
    nonresponse_codes: list[float]
    nonresponse_replaced: int = Field(ge=0)


class ExtractMetadata(StrictModel):
    dataset_id: str
    source: Literal["NHANES"]
    cycle: list[str]
    filters_applied: list[str]
    extraction_date: str
    row_count: int = Field(ge=300, le=5000)
    column_count: int = Field(ge=8, le=30)
    columns: dict[str, ColumnMetadata]
    time_column: str | None
    weight_columns: list[str]
    id_columns: list[str]
    design_columns: list[str]
    sampling_seed: int
    coverage: str
    duplicates_removed: int
    sources: list[SourceRecord]
    contamination_screen: ContaminationScreen
    license: dict[str, str]
    extract_sha256: str
    cohort_sha256: str
    transformations: list[str]
    pandas_version: str


class CodebookParser(HTMLParser):
    """Read variable-specific refusal codes from CDC frequency tables only."""

    def __init__(self) -> None:
        super().__init__()
        self.codes: dict[str, list[float]] = {}
        self.variable: str | None = None
        self.cells: list[str] = []
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h3":
            name = dict(attrs).get("id", "") or ""
            self.variable = name if re.fullmatch(r"[A-Z][A-Z0-9_]*", name) else None
            if self.variable:
                self.codes.setdefault(self.variable, [])
        if tag == "tr":
            self.cells = []
        if tag in {"td", "th"}:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.cell is not None:
            self.cells.append(" ".join("".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.variable and len(self.cells) >= 2:
            label = self.cells[1].casefold().replace("’", "'")
            if label in {"refused", "don't know", "dont know"}:
                try:
                    code = float(self.cells[0])
                except ValueError:
                    raise ValueError(f"unsupported nonresponse code in {self.variable}") from None
                self.codes[self.variable].append(code)


def load_plan(path: Path | str = DEFAULT_PLAN) -> PilotPlan:
    """Validate the approved plan before any data is read or written."""
    return PilotPlan.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def sha256(path: Path) -> str:
    """Hash a file without reading the entire source into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fetch(url: str, path: Path, timeout: int) -> None:
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with (
            urllib.request.urlopen(url, timeout=timeout) as response,  # noqa: S310
            temporary.open("wb") as target,
        ):
            while block := response.read(1024 * 1024):
                target.write(block)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def source_urls(component: str, cycle: Cycle) -> tuple[str, str]:
    """Resolve one official public data file and its matching codebook."""
    base = BASE_URL.format(year=cycle.year, component=component)
    return f"{base}.xpt", f"{base}.htm"


def prepare_sources(plan: PilotPlan, raw_dir: Path) -> None:
    """Cache only the official components needed by the approved pilot."""
    from concurrent.futures import ThreadPoolExecutor

    jobs: dict[Path, str] = {}
    for spec in plan.extracts:
        for suffix in spec.cycles:
            for module in ["DEMO", *spec.modules]:
                component = f"{module}_{suffix}"
                data_url, doc_url = source_urls(component, plan.cycles[suffix])
                for url, extension in ((data_url, "xpt"), (doc_url, "htm")):
                    jobs[raw_dir / f"{component}.{extension}"] = url
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(_fetch, url, path, plan.download_timeout_seconds)
            for path, url in jobs.items()
        ]
        for future in futures:
            future.result()


def read_component(
    component: str, cycle: Cycle, raw_dir: Path
) -> tuple[pd.DataFrame, dict[str, list[float]], SourceRecord]:
    """Read a real SAS component and its documented per-column nonresponse codes."""
    data_path, doc_path = raw_dir / f"{component}.xpt", raw_dir / f"{component}.htm"
    frame = pd.read_sas(data_path, format="xport", encoding="utf-8")
    parser = CodebookParser()
    parser.feed(doc_path.read_text(encoding="utf-8-sig"))
    if not parser.codes or "SEQN" not in parser.codes:
        raise ValueError(f"no variable codebook found for {component}")
    data_url, codebook_url = source_urls(component, cycle)
    return (
        frame,
        parser.codes,
        SourceRecord(
            component=component,
            cycle=cycle.label,
            data_url=data_url,
            codebook_url=codebook_url,
            data_sha256=sha256(data_path),
            codebook_sha256=sha256(doc_path),
        ),
    )


def assemble_extract(
    spec: ExtractSpec, plan: PilotPlan, raw_dir: Path
) -> tuple[pd.DataFrame, dict[str, list[float]], list[SourceRecord], int]:
    """Join whole adult records, select rows reproducibly, and preserve real missingness.

    No complete-case filtering, imputation, winsorization, column renaming,
    independent column shuffling or relationship injection is performed.
    """
    roles = plan.common_columns | spec.columns
    all_codes: dict[str, list[float]] = {name: [] for name in roles}
    records: list[SourceRecord] = []
    frames: list[pd.DataFrame] = []
    duplicates = 0
    for suffix in spec.cycles:
        cycle = plan.cycles[suffix]
        parts: dict[str, pd.DataFrame] = {}
        cycle_codes: dict[str, list[float]] = {}
        for module in ["DEMO", *spec.modules]:
            component = f"{module}_{suffix}"
            data, codes, provenance = read_component(component, cycle, raw_dir)
            records.append(provenance)
            selected = [name for name in roles if name in data.columns]
            for name in selected:
                if name not in codes:
                    raise ValueError(f"missing codebook for {component}.{name}")
                cycle_codes[name] = codes[name]
            columns = list(dict.fromkeys(["SEQN", *selected]))
            data = data[columns]
            before = len(data)
            data = data.drop_duplicates()
            duplicates += before - len(data)
            if data["SEQN"].isna().any() or data["SEQN"].duplicated().any():
                raise ValueError(f"invalid or conflicting respondent IDs in {component}")
            parts[module] = data
        # The first listed module defines eligibility; secondary modules are left joins.
        frame = parts[spec.modules[0]]
        for module in ["DEMO", *spec.modules[1:]]:
            extra = [name for name in parts[module] if name not in frame or name == "SEQN"]
            frame = frame.merge(parts[module][extra], on="SEQN", how="left", validate="one_to_one")
        if frame["RIDAGEYR"].isna().any():
            raise ValueError(
                "a source respondent has no demographic age; cannot silently filter it"
            )
        frame = frame.loc[frame["RIDAGEYR"] >= plan.min_age, list(roles)].copy()
        if len(frame) < spec.rows_per_cycle:
            raise ValueError(f"{spec.dataset_id}: only {len(frame)} eligible rows in {cycle.label}")
        # Whole-row sampling preserves real joint relationships and paired missingness.
        frame = (
            frame.sort_values("SEQN")
            .sample(n=spec.rows_per_cycle, random_state=plan.seed + cycle.year)
            .sort_values("SEQN")
        )
        for name in roles:
            column_codes = cycle_codes.get(name)
            if column_codes is None:
                raise ValueError(f"no source component supplies {name}")
            all_codes[name] = sorted(set(all_codes[name]) | set(column_codes))
        # Apply each cycle's own codes; a code valid in another cycle must remain valid there.
        frame.attrs["nonresponse_counts"] = {
            name: int(frame[name].isin(cycle_codes[name]).sum()) for name in roles
        }
        for name in roles:
            frame[name] = frame[name].mask(frame[name].isin(cycle_codes[name]))
        frames.append(frame)
    counts = {
        name: sum(item.attrs["nonresponse_counts"][name] for item in frames) for name in roles
    }
    # Remove attrs before concat: pandas compares attrs, which is not a merge of audit counts.
    for frame in frames:
        frame.attrs = {}
    result = pd.concat(frames, ignore_index=True)
    before = len(result)
    result = result.drop_duplicates().sort_values(["SDDSRVYR", "SEQN"]).reset_index(drop=True)
    duplicates += before - len(result)
    result.attrs["nonresponse_counts"] = counts
    return result, all_codes, records, duplicates


def build_extract(
    spec: ExtractSpec, plan: PilotPlan, raw_dir: Path, output_root: Path
) -> ExtractMetadata:
    """Write UTF-8 extract.csv plus validated metadata.json, with a content-hash handoff."""
    frame, codes, sources, duplicates = assemble_extract(spec, plan, raw_dir)
    directory = output_root / spec.dataset_id
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "extract.csv"
    temporary = directory / f".extract.{uuid4().hex}.tmp"
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8", lineterminator="\n", na_rep="")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    screening = screen_source("NHANES", [record.data_url for record in sources])
    if not screening.accepted:
        raise ValueError("source provenance failed screening")
    cohort = frame[["SDDSRVYR", "SEQN"]].to_csv(index=False, lineterminator="\n")
    metadata = ExtractMetadata(
        dataset_id=spec.dataset_id,
        source="NHANES",
        cycle=[plan.cycles[suffix].label for suffix in spec.cycles],
        filters_applied=[
            f"RIDAGEYR >= {plan.min_age}",
            f"Primary module: {spec.modules[0]}; left join remaining modules on SEQN",
            f"Whole-row sample: {spec.rows_per_cycle} per cycle, seed + cycle year",
        ],
        extraction_date=datetime.now(UTC).isoformat(),
        row_count=len(frame),
        column_count=len(frame.columns),
        columns={
            name: ColumnMetadata(
                dtype=role,
                missing_pct=float(frame[name].isna().mean() * 100),
                missing_count=int(frame[name].isna().sum()),
                nonresponse_codes=codes[name],
                nonresponse_replaced=frame.attrs["nonresponse_counts"][name],
            )
            for name, role in (plan.common_columns | spec.columns).items()
        },
        time_column=spec.time_column,
        weight_columns=plan.weight_columns,
        id_columns=plan.id_columns,
        design_columns=plan.design_columns,
        sampling_seed=plan.seed,
        coverage=spec.coverage,
        duplicates_removed=duplicates,
        sources=sources,
        contamination_screen=screening,
        license={
            "access": "Public-use NHANES; CDC-produced materials generally public domain",
            "policy_url": "https://www.cdc.gov/other/agencymaterials.html",
            "restrictions": "No re-identification; no restricted files or NFHS microdata",
        },
        extract_sha256=sha256(target),
        cohort_sha256=hashlib.sha256(cohort.encode()).hexdigest(),
        transformations=[
            "Documented per-column, per-cycle Refused/Don't know codes -> empty CSV fields",
            "Exact duplicate removal only; real missingness retained; original column names",
            "No imputation, extra value filtering, column shuffling or injection",
            "Pooled cycle weights retained unchanged; not a population-estimation dataset",
        ],
        pandas_version=pd.__version__,
    )
    write_json(directory / "metadata.json", metadata.model_dump(mode="json"))
    return metadata


def write_json(path: Path, value: object) -> None:
    """Atomically write readable JSON without NaN or platform-dependent newlines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_extract(directory: Path) -> tuple[pd.DataFrame, ExtractMetadata]:
    """Reject altered/incomplete handoffs and validate shape, columns and missingness."""
    metadata = ExtractMetadata.model_validate_json((directory / "metadata.json").read_text("utf-8"))
    target = directory / "extract.csv"
    if sha256(target) != metadata.extract_sha256:
        raise ValueError("extract content does not match metadata SHA-256")
    frame = pd.read_csv(target, encoding="utf-8", keep_default_na=False, na_values=[""])
    if list(frame.columns) != list(metadata.columns) or frame.shape != (
        metadata.row_count,
        metadata.column_count,
    ):
        raise ValueError("extract columns/shape do not match metadata")
    if any(
        int(frame[name].isna().sum()) != item.missing_count
        for name, item in metadata.columns.items()
    ):
        raise ValueError("extract missingness does not match metadata")
    if any(
        not math.isclose(float(frame[name].isna().mean() * 100), item.missing_pct)
        for name, item in metadata.columns.items()
    ):
        raise ValueError("extract missing percentages do not match metadata")
    if not metadata.contamination_screen.accepted:
        raise ValueError("extract has not passed provenance screening")
    return frame, metadata


def schema_for_extract(frame: pd.DataFrame, metadata: ExtractMetadata) -> SchemaProfile:
    """Use documented roles, exclude survey design fields, and retain the approved cycle axis."""
    config = load_config().schema_inference
    schema = infer_schema(frame, config)
    excluded = set(metadata.id_columns + metadata.weight_columns + metadata.design_columns)
    for name, item in metadata.columns.items():
        profile = schema.columns[name]
        role = ColumnRole.ID_LIKE if item.dtype == "id" else ColumnRole(item.dtype)
        usable = (
            name not in excluded
            and profile.n_non_null >= config.min_non_null
            and profile.n_unique >= 2
        )
        schema.columns[name] = profile.model_copy(
            update={
                "role": role,
                "confidence": 1.0,
                "usable_for_hypotheses": usable,
                "is_time_like": name == metadata.time_column,
                "levels": sorted(str(value) for value in frame[name].dropna().unique())
                if role in {ColumnRole.CATEGORICAL, ColumnRole.ORDINAL}
                else [],
                "reasons": [
                    *profile.reasons,
                    "Role from the approved extract's CDC codebook metadata",
                ],
            }
        )
    return schema
