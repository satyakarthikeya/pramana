"""Demo dataset construction, offline: synthetic NHANES-shaped components, no network."""

import numpy as np
import pandas as pd
import pytest

from pramana.analysis.benchmark.demo_dataset import (
    DemoSpec,
    assemble_subset,
    inject_false_correlation,
    load_demo_spec,
)
from pramana.analysis.config import load_config


def _spec(**overrides: object) -> DemoSpec:
    values: dict[str, object] = {
        "seed": 7,
        "n_rows": 500,
        "min_age_years": 20,
        "decoy_column": "birth_moon_phase_pct",
        "decoy_target": "hba1c_pct",
        "decoy_pilot_rows": 40,
        "decoy_target_rho": 0.30,
    }
    values.update(overrides)
    return DemoSpec.model_validate(values)


def _components(n: int = 900) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(0)
    seqn = np.arange(1, n + 1, dtype=float)
    age = rng.integers(10, 80, n).astype(float)
    bmi = rng.normal(28, 5, n)
    return {
        "DEMO_J": pd.DataFrame(
            {
                "SEQN": seqn,
                "RIDAGEYR": age,
                "RIAGENDR": rng.choice([1.0, 2.0], n),
                "RIDRETH3": rng.choice([1.0, 3.0, 4.0], n),
                "INDFMPIR": rng.uniform(0, 5, n),
            }
        ),
        "BMX_J": pd.DataFrame(
            {"SEQN": seqn, "BMXBMI": bmi, "BMXWAIST": bmi * 3.4, "BMXHT": rng.normal(168, 9, n)}
        ),
        "BPX_J": pd.DataFrame(
            {
                "SEQN": seqn,
                "BPXSY1": 100 + 0.5 * age + rng.normal(0, 10, n),
                "BPXDI1": np.where(np.arange(n) % 50 == 0, 0.0, rng.normal(72, 9, n)),
            }
        ),
        "GHB_J": pd.DataFrame({"SEQN": seqn, "LBXGH": np.round(rng.normal(5.7, 0.8, n), 1)}),
        "TCHOL_J": pd.DataFrame({"SEQN": seqn, "LBXTC": rng.normal(190, 35, n)}),
        "HDL_J": pd.DataFrame({"SEQN": seqn, "LBDHDD": 80 - bmi + rng.normal(0, 8, n)}),
    }


def test_the_committed_spec_loads_and_names_an_adult_subset_in_range() -> None:
    spec = load_demo_spec()
    assert 500 <= spec.n_rows <= 2000
    assert spec.decoy_target_rho >= 2 * load_config().hypotheses.min_abs_correlation


def test_assembly_is_adult_only_labelled_reproducible_and_drops_the_identifier() -> None:
    spec = _spec()
    first = assemble_subset(_components(), spec)
    second = assemble_subset(_components(), spec)

    pd.testing.assert_frame_equal(first, second)
    assert len(first) == spec.n_rows
    assert "SEQN" not in first.columns
    assert first["age_years"].min() >= spec.min_age_years
    assert set(first["sex"].unique()) <= {"male", "female"}
    assert (first["diastolic_bp"].dropna() > 0).all()


def test_assembly_refuses_a_spec_the_data_cannot_fill() -> None:
    with pytest.raises(ValueError, match="eligible adults"):
        assemble_subset(_components(n=300), _spec())


def test_the_decoy_carries_the_planted_rho_on_pilot_rows_only() -> None:
    spec = _spec()
    frame = assemble_subset(_components(), spec)
    injected, planted = inject_false_correlation(frame, spec)

    decoy = injected[spec.decoy_column]
    assert decoy.notna().sum() == spec.decoy_pilot_rows
    assert decoy.dropna().between(0, 100).all()
    assert spec.decoy_column not in frame.columns  # input untouched

    pair = injected[[spec.decoy_target, spec.decoy_column]].dropna()
    observed = pair[spec.decoy_target].corr(pair[spec.decoy_column], method="spearman")
    assert observed == pytest.approx(planted.in_sample_rho)
    assert abs(observed - spec.decoy_target_rho) < 0.02
    assert planted.expected_verdict == "REJECT"
    assert planted.n_observations == spec.decoy_pilot_rows


def test_injection_is_seeded() -> None:
    spec = _spec()
    frame = assemble_subset(_components(), spec)
    first, _ = inject_false_correlation(frame, spec)
    second, _ = inject_false_correlation(frame, spec)
    pd.testing.assert_series_equal(first[spec.decoy_column], second[spec.decoy_column])

    other, _ = inject_false_correlation(frame, _spec(seed=8))
    assert not first[spec.decoy_column].equals(other[spec.decoy_column])


def test_injection_refuses_to_overwrite_an_existing_column() -> None:
    spec = _spec()
    frame = assemble_subset(_components(), spec)
    injected, _ = inject_false_correlation(frame, spec)
    with pytest.raises(ValueError, match="already exists"):
        inject_false_correlation(injected, spec)
