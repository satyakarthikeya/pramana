import pytest

from pramana.analysis.benchmark.contamination import screen_source
from pramana.analysis.benchmark.curation import curate_manifest


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
