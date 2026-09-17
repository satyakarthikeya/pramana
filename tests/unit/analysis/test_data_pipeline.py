from pathlib import Path

import pandas as pd
import pytest

from pramana.analysis.cleaning import clean_dataset
from pramana.analysis.ingestion import get_dataset_metadata, load_dataset
from pramana.analysis.profiling import profile_dataset


def test_ingestion_metadata_and_missing_markers(tmp_path: Path) -> None:
    source = tmp_path / "sample.csv"
    source.write_text("group,value\nA,1\nA,?\nB,3\n", encoding="utf-8")

    frame = load_dataset(source)
    metadata = get_dataset_metadata(frame, source_path=source)

    assert frame["value"].isna().sum() == 1
    assert metadata.rows == 3
    assert metadata.columns == 2
    assert metadata.missing_values["value"] == 1


def test_ingestion_rejects_unsupported_and_oversized_inputs(tmp_path: Path) -> None:
    source = tmp_path / "sample.json"
    source.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="CSV and XLSX"):
        load_dataset(source)

    csv_source = tmp_path / "large.csv"
    csv_source.write_text("value\n1\n2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="row limit"):
        load_dataset(csv_source, max_rows=1)


def test_cleaning_preserves_input_and_reports_quality_findings() -> None:
    source = pd.DataFrame(
        {
            "constant": ["x", "x", "x"],
            "near_constant": ["x", "x", "y"],
            "identifier": ["a", "b", "c"],
            "label": [" North ", "north", "South"],
            "score": [1.0, 2.0, 3.0],
        }
    )

    cleaned, report = clean_dataset(source, near_constant_threshold=0.60)

    assert list(cleaned.columns) == ["near_constant", "identifier", "label", "score"]
    assert source["constant"].tolist() == ["x", "x", "x"]
    assert report.columns_removed == [
        {"column": "constant", "reason": "constant column"}
    ]
    assert report.near_constant_columns[0]["column"] == "near_constant"
    assert report.identifier_columns[0]["column"] == "identifier"
    assert report.inconsistent_categorical_labels[0]["column"] == "label"


def test_profiling_returns_statistics_and_relationship_evidence() -> None:
    frame = pd.DataFrame(
        {
            "group": ["a", "a", "b", "b", "c", "c"],
            "x": [1, 2, 3, 4, 5, 6],
            "y": [2, 4, 6, 8, 10, 12],
        }
    )

    profile = profile_dataset(frame)

    assert profile["numeric_profiles"]["x"]["mean"] == 3.5
    assert any(
        item["relationship_type"] == "numeric_numeric_association"
        for item in profile["relationships"]
    )
    assert any(
        item["relationship_type"] == "categorical_numeric_group_difference"
        for item in profile["relationships"]
    )
