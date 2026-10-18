"""Known-answer cleaning and provenance checks for the unshuffled source handoff."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from pramana.analysis.benchmark import curation
from pramana.analysis.benchmark.contamination import screen_source
from pramana.analysis.config import load_config
from pramana.analysis.hypotheses.generation import generate_candidates


@pytest.fixture
def fake_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = curation.load_plan()

    def read(component: str, cycle: curation.Cycle, _root: Path) -> tuple:
        size = 400
        rng = np.random.default_rng(41)
        ids = np.arange(size) + cycle.year * 1000
        common = {name: rng.normal(size=size) for name in plan.common_columns}
        common.update(
            {
                "SEQN": ids,
                "SDDSRVYR": np.full(size, (cycle.year - 1997) // 2),
                "RIDAGEYR": np.r_[np.full(20, 10), np.full(size - 20, 40)],
                "RIAGENDR": rng.choice([1, 2], size),
                "RIDRETH3": np.full(size, 7),
                "DMDEDUC2": np.full(size, 9),
            }
        )
        module_columns = {name for item in plan.extracts for name in item.columns}
        extra = {name: rng.normal(size=size) for name in module_columns}
        extra["BMXWT"] = np.full(size, 7777.0)  # Valid numeric value, not a generic sentinel.
        extra["BMXBMI"] = rng.normal(25, 4, size)
        extra["BMXBMI"][::5] = np.nan
        data = pd.DataFrame(common if component.startswith("DEMO") else {"SEQN": ids, **extra})
        codes = {name: [7.0, 9.0] if name == "DMDEDUC2" else [] for name in data}
        data_url, codebook_url = curation.source_urls(component, cycle)
        record = curation.SourceRecord(
            component=component,
            cycle=cycle.label,
            data_url=data_url,
            codebook_url=codebook_url,
            data_sha256="0" * 64,
            codebook_sha256="1" * 64,
        )
        return data, codes, record

    monkeypatch.setattr(curation, "read_component", read)


def test_plan_is_exactly_the_approved_balanced_pilot() -> None:
    plan = curation.load_plan()
    assert len(plan.extracts) == 10
    assert [
        sum(spec.coverage == kind for spec in plan.extracts)
        for kind in ("numeric_pairs", "group_differences", "trends")
    ] == [3, 3, 3]
    raw = plan.model_dump()
    raw["extracts"][0]["dataset_id"] = "../../outside"
    with pytest.raises(ValidationError):
        curation.PilotPlan.model_validate(raw)


def test_full_plan_preserves_pilot_and_adds_distinct_source_definitions() -> None:
    pilot = curation.load_plan()
    full = curation.load_plan(curation.ROOT / "configs/benchmark_40.yaml")
    assert full.extracts[:10] == pilot.extracts
    assert len(full.extracts) == 40
    assert sum(spec.coverage == "trends" for spec in full.extracts) == 9
    raw = full.model_dump()
    raw["extracts"][-1] = dict(raw["extracts"][0], dataset_id="duplicate_source")
    with pytest.raises(ValidationError, match="distinct"):
        curation.PilotPlan.model_validate(raw)
    raw = full.model_dump()
    raw["phase"] = "pilot"
    with pytest.raises(ValidationError, match="phase"):
        curation.PilotPlan.model_validate(raw)


def test_codebook_codes_are_per_variable_not_blanket_numbers() -> None:
    parser = curation.CodebookParser()
    parser.feed("""<h3 id="EDUC">education</h3><table>
      <tr><td>7</td><td>Refused</td></tr><tr><td>9</td><td>Don’t know</td></tr></table>
      <h3 id="RACE">race</h3><table><tr><td>7</td><td>Other / multiracial</td></tr></table>""")
    assert parser.codes == {"EDUC": [7.0, 9.0], "RACE": []}


def test_real_missingness_and_valid_codes_survive_whole_row_sampling(
    fake_sources: None,
    tmp_path: Path,
) -> None:
    plan = curation.load_plan()
    spec = plan.extracts[0].model_copy(update={"rows_per_cycle": 300})
    frame, codes, _sources, _duplicates = curation.assemble_extract(spec, plan, tmp_path)
    assert len(frame) == 300
    assert (frame["RIDAGEYR"] == 40).all()
    assert (frame["RIDRETH3"] == 7).all()
    assert (frame["BMXWT"] == 7777).all()
    assert frame["DMDEDUC2"].isna().all()
    assert frame["BMXBMI"].isna().any()
    assert codes["RIDRETH3"] == []
    assert frame.attrs["nonresponse_counts"]["DMDEDUC2"] == 300
    again, *_ = curation.assemble_extract(spec, plan, tmp_path)
    pd.testing.assert_frame_equal(frame, again)


def test_csv_and_metadata_roundtrip_is_reproducible_and_tampering_is_refused(
    fake_sources: None,
    tmp_path: Path,
) -> None:
    plan = curation.load_plan()
    spec = plan.extracts[0].model_copy(update={"rows_per_cycle": 300})
    first = curation.build_extract(spec, plan, tmp_path, tmp_path / "out")
    path = tmp_path / "out" / spec.dataset_id
    frame, metadata = curation.load_extract(path)
    assert metadata == first
    assert metadata.columns["DMDEDUC2"].missing_pct == 100
    assert frame["DMDEDUC2"].isna().all()
    again = curation.build_extract(spec, plan, tmp_path, tmp_path / "out")
    assert again.extract_sha256 == first.extract_sha256
    assert again.cohort_sha256 == first.cohort_sha256
    with (path / "extract.csv").open("a") as stream:
        stream.write("tampered\n")
    with pytest.raises(ValueError, match="SHA-256"):
        curation.load_extract(path)


def test_metadata_hash_alone_does_not_hide_changed_missingness(
    fake_sources: None,
    tmp_path: Path,
) -> None:
    plan = curation.load_plan()
    spec = plan.extracts[0].model_copy(update={"rows_per_cycle": 300})
    curation.build_extract(spec, plan, tmp_path, tmp_path / "out")
    directory = tmp_path / "out" / spec.dataset_id
    metadata = json.loads((directory / "metadata.json").read_text("utf-8"))
    metadata["columns"]["DMDEDUC2"]["missing_count"] = 0
    curation.write_json(directory / "metadata.json", metadata)
    with pytest.raises(ValueError, match="missingness"):
        curation.load_extract(directory)


def test_cycle_axis_and_survey_exclusions_reach_the_real_proposer(
    fake_sources: None,
    tmp_path: Path,
) -> None:
    plan = curation.load_plan()
    spec = plan.extracts[6].model_copy(update={"rows_per_cycle": 300})
    curation.build_extract(spec, plan, tmp_path, tmp_path / "out")
    frame, metadata = curation.load_extract(tmp_path / "out" / spec.dataset_id)
    schema = curation.schema_for_extract(frame, metadata)
    assert schema.columns["SDDSRVYR"].is_time_like
    for name in metadata.id_columns + metadata.weight_columns + metadata.design_columns:
        assert not schema.columns[name].usable_for_hypotheses
    # Plant only in this synthetic test fixture to exercise the proposer, never in real extracts.
    frame["BMXBMI"] = frame["SDDSRVYR"] * 5 + np.random.default_rng(11).normal(size=len(frame))
    candidates = generate_candidates(
        frame, schema, load_config().hypotheses, dataset_ref="synthetic"
    )
    assert any(item.claim_type.value == "trend" for item in candidates)
    excluded = set(metadata.id_columns + metadata.weight_columns + metadata.design_columns)
    assert all(not excluded.intersection(item.variables) for item in candidates)
    assert all("verdict" not in item.analysis_evidence for item in candidates)


@pytest.mark.parametrize(
    "source,url",
    [
        ("MIMIC-IV", "https://physionet.org/"),
        ("NHANES", "https://evil.example/Nchs/Data/Nhanes/Public/BMX_J.xpt"),
        ("iris", "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/BMX_J.xpt"),
    ],
)
def test_other_sources_and_famous_benchmarks_are_refused(source: str, url: str) -> None:
    assert not screen_source(source, [url]).accepted
