import pytest
import pandas as pd

from pramana.analysis.benchmark.contamination import screen_source
from pramana.analysis.benchmark.curation import curate_manifest
from pramana.analysis.benchmark.demo_dataset import build_demo_from_diabetes


def _source(index: int, *, name: str | None = None) -> dict[str, object]:
    return {
        "dataset_id": f"nhanes-{index:02d}",
        "name": name or f"NHANES public extract {index:02d}",
        "source": "NHANES",
        "source_url": "https://wwwn.cdc.gov/nchs/nhanes/",
        "source_family": "NHANES",
        "seed": 20260817 + index,
    }


def test_contamination_screen_rejects_famous_and_forbidden_sources() -> None:
    famous = screen_source(
        dataset_id="iris",
        name="Iris",
        source="scikit-learn",
    )
    forbidden = screen_source(
        dataset_id="health",
        name="Clinical extract",
        source="MIMIC-IV PhysioNet",
    )

    assert not famous.accepted
    assert not forbidden.accepted
    assert "forbidden_source:mimic-iv" in forbidden.matched_rules


def test_curate_manifest_requires_exactly_40_clean_sources() -> None:
    manifest = curate_manifest([_source(index) for index in range(40)])

    manifest.validate_ready()
    assert len(manifest.datasets) == 40
    assert len({dataset.dataset_id for dataset in manifest.datasets}) == 40


def test_curate_manifest_fails_closed_for_rejected_source() -> None:
    with pytest.raises(ValueError, match="rejected sources"):
        curate_manifest([_source(index) for index in range(39)] + [_source(39, name="Titanic")])


def test_build_demo_from_diabetes_is_bounded_and_reproducible(tmp_path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    pd.DataFrame(
        {
            "age": ["[20-30)"] * 600,
            "gender": ["Female", "Male"] * 300,
            "race": ["Caucasian"] * 600,
            "time_in_hospital": list(range(1, 601)),
            "num_lab_procedures": list(range(600)),
            "num_medications": list(range(600)),
            "number_outpatient": [0] * 600,
            "number_emergency": [0] * 600,
            "number_inpatient": [0] * 600,
            "number_diagnoses": [5] * 600,
            "readmitted": ["NO"] * 600,
        }
    ).to_csv(source_dir / "diabetic_data.csv", index=False)

    first = build_demo_from_diabetes(source_dir, tmp_path / "first.csv", rows=500, seed=7)
    second = build_demo_from_diabetes(source_dir, tmp_path / "second.csv", rows=500, seed=7)

    first_frame = pd.read_csv(first)
    second_frame = pd.read_csv(second)
    assert first_frame.equals(second_frame)
    assert first_frame.shape == (500, 12)
    assert "injected_false_signal" in first_frame.columns
    assert first_frame["num_lab_procedures"].corr(
        first_frame["injected_false_signal"]
    ) < 0.15
