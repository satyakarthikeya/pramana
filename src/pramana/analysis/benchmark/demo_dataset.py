"""Build the demo subset (~500-2000 rows, 8-15 cols) and inject ONE false
correlation, seeded and reproducible, for the gateway to reject on stage.

What the demo must show (PROJECT.md 7)
--------------------------------------
Real signal survives, fake signal dies, in one run. The real signal is NHANES
2017-2018 adults, where two textbook relationships are present at full strength:

  * systolic blood pressure rises with age;
  * HDL cholesterol falls as BMI rises.

Why the false correlation is NOT a shuffled column
--------------------------------------------------
A shuffled copy of a real column has in-sample |rho| near zero, so the analysis
module's `min_abs_correlation` pre-filter drops it before the gateway ever sees it.
The demo would then show nothing being rejected. The decoy has to carry a REAL
in-sample association large enough to be proposed.

It also cannot be a well-powered association. The gateway gates on a permutation
p-value, BH-FDR across the batch, and an effect floor, all on the same frame the
scan read. A |rho| of 0.3 on 1,500 rows clears every one of those, so a decoy
planted across the full frame would PASS -- correctly, since the association would
be real in this data. The current gateway has no held-out or confounder check that
could reject it.

So the decoy is the failure mode exploratory scans actually produce: a column
measured on a small subsample (`decoy_pilot_rows`) where, among dozens of pairs
scanned, one shows an impressive-looking rho. Here that rho is planted, seeded, and
calibrated to `decoy_target_rho` -- twice the pre-filter, so it is certainly
proposed -- and on 40 rows it is indistinguishable from chance. The column name
(birth-date moon phase) makes the claim visibly absurd to a human audience.

Data policy
-----------
Raw NHANES files are downloaded into the gitignored `data/raw/nhanes/` and never
committed (AGENTS.md 6). NHANES is US public-domain data.

Owner: P. Rohith
Scope: scope/SCOPE_P_Rohith.md 4 step 8
"""

from __future__ import annotations

import urllib.request
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.config import DEFAULT_CONFIG_PATH

#: NHANES 2017-2018 ("J" cycle) public-use files.
NHANES_BASE_URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/{name}.xpt"

#: Component file -> {NHANES variable: demo column}. SEQN is the join key everywhere.
NHANES_COMPONENTS: Mapping[str, Mapping[str, str]] = {
    "DEMO_J": {
        "RIDAGEYR": "age_years",
        "RIAGENDR": "sex",
        "RIDRETH3": "race_ethnicity",
        "INDFMPIR": "income_poverty_ratio",
    },
    "BMX_J": {"BMXBMI": "bmi", "BMXWAIST": "waist_cm", "BMXHT": "height_cm"},
    "BPX_J": {"BPXSY1": "systolic_bp", "BPXDI1": "diastolic_bp"},
    "GHB_J": {"LBXGH": "hba1c_pct"},
    "TCHOL_J": {"LBXTC": "total_chol"},
    "HDL_J": {"LBDHDD": "hdl_chol"},
}

_SEX_LABELS = {1.0: "male", 2.0: "female"}
_RACE_LABELS = {
    1.0: "mexican_american",
    2.0: "other_hispanic",
    3.0: "non_hispanic_white",
    4.0: "non_hispanic_black",
    6.0: "non_hispanic_asian",
    7.0: "other_or_multiracial",
}

#: Rows must have these to enter the subset: the two planted true pairs plus the
#: decoy's target, so none of the relationships the demo asserts runs on thin data.
_REQUIRED = ("age_years", "systolic_bp", "bmi", "hdl_chol", "hba1c_pct")


class DemoSpec(BaseModel):
    """The `benchmark.demo` section of `configs/analysis.yaml`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int
    n_rows: int = Field(ge=500, le=2000)
    min_age_years: int = Field(ge=0)
    decoy_column: str = Field(min_length=1)
    decoy_target: str = Field(min_length=1)
    decoy_pilot_rows: int = Field(ge=10)
    decoy_target_rho: float = Field(gt=0.0, lt=1.0)


class PlantedRelationship(BaseModel):
    """One relationship the demo asserts about, and what the gate should conclude."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    variables: tuple[str, str]
    expected_verdict: str
    rationale: str
    in_sample_rho: float
    n_observations: int


class DemoManifest(BaseModel):
    """What was built, from what, and what the run is expected to show."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    spec: DemoSpec
    n_rows: int
    columns: list[str]
    expected_pass: list[PlantedRelationship]
    injected_false: PlantedRelationship


def load_demo_spec(path: Path | str = DEFAULT_CONFIG_PATH) -> DemoSpec:
    """Read the demo spec; a missing or misspelled key fails here, not mid-build."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return DemoSpec.model_validate(raw["benchmark"]["demo"])


def download_nhanes(raw_dir: Path | str) -> dict[str, Path]:
    """Fetch each NHANES component into `raw_dir`, skipping files already present.

    Guarantees: returns a path for every component in `NHANES_COMPONENTS`, and never
    re-downloads a file that exists, so a rebuild is offline after the first run.
    """
    target = Path(raw_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name in NHANES_COMPONENTS:
        path = target / f"{name}.xpt"
        if not path.is_file():
            partial = path.with_suffix(".part")
            urllib.request.urlretrieve(NHANES_BASE_URL.format(name=name), partial)  # noqa: S310
            partial.replace(path)
        paths[name] = path
    return paths


def read_components(paths: Mapping[str, Path]) -> dict[str, pd.DataFrame]:
    """Load each XPT file into a frame, keeping SEQN and the mapped variables only."""
    frames: dict[str, pd.DataFrame] = {}
    for name, variables in NHANES_COMPONENTS.items():
        raw = pd.read_sas(paths[name], format="xport")
        frames[name] = raw[["SEQN", *variables]]
    return frames


def assemble_subset(components: Mapping[str, pd.DataFrame], spec: DemoSpec) -> pd.DataFrame:
    """Join the components into one adult-only frame of `spec.n_rows` rows.

    Guarantees: readable column names; coded categoricals mapped to labels; NHANES's
    diastolic reading of 0 (recorded when it could not be measured) set to missing
    rather than left as a physiologically impossible value; SEQN dropped, since an
    identifier is not a variable; and the same `spec` always yields the same rows.
    """
    frame = components["DEMO_J"]
    for name in NHANES_COMPONENTS:
        if name != "DEMO_J":
            frame = frame.merge(components[name], on="SEQN", how="left")
    renames = {
        old: new for variables in NHANES_COMPONENTS.values() for old, new in variables.items()
    }
    frame = frame.rename(columns=renames)

    frame["sex"] = frame["sex"].map(_SEX_LABELS)
    frame["race_ethnicity"] = frame["race_ethnicity"].map(_RACE_LABELS)
    frame.loc[frame["diastolic_bp"] <= 0, "diastolic_bp"] = np.nan

    adults = frame[frame["age_years"] >= spec.min_age_years].dropna(subset=list(_REQUIRED))
    if len(adults) < spec.n_rows:
        raise ValueError(
            f"only {len(adults)} eligible adults; the demo spec asks for {spec.n_rows}"
        )
    sample = adults.sample(n=spec.n_rows, random_state=spec.seed).sort_values("SEQN")
    return sample.drop(columns="SEQN").reset_index(drop=True)


def inject_false_correlation(
    frame: pd.DataFrame, spec: DemoSpec
) -> tuple[pd.DataFrame, PlantedRelationship]:
    """Add the decoy column: present on `decoy_pilot_rows` rows, missing elsewhere.

    On those rows its Spearman rho with `decoy_target` is calibrated as close to
    `decoy_target_rho` as a fine grid allows. The values themselves are draws from
    Uniform(0, 100) (a moon-illumination percentage) assigned in rank order, so
    they look like a measurement and the calibrated ranks are kept exactly.

    Guarantees: `frame` is not modified; the same `(frame, spec)` produces the same
    column; and the returned relationship records the rho actually planted, not
    the one requested.
    """
    if spec.decoy_column in frame.columns:
        raise ValueError(f"{spec.decoy_column!r} already exists; refusing to overwrite it")
    rng = np.random.default_rng(spec.seed)
    eligible = frame.index[frame[spec.decoy_target].notna()]
    pilot = np.sort(rng.choice(eligible, size=spec.decoy_pilot_rows, replace=False))

    target = frame.loc[pilot, spec.decoy_target]
    target_ranks = target.rank().to_numpy(dtype=float)
    signal = (target_ranks - target_ranks.mean()) / target_ranks.std()
    noise = rng.standard_normal(spec.decoy_pilot_rows)

    best_values, best_rho = noise, 0.0
    for weight in np.linspace(0.0, 2.0, 2001):
        mixed = pd.Series(weight * signal + noise, index=pilot)
        rho = float(mixed.corr(target, method="spearman"))
        if abs(rho - spec.decoy_target_rho) < abs(best_rho - spec.decoy_target_rho):
            best_values, best_rho = mixed.to_numpy(), rho

    readings = np.round(np.sort(rng.uniform(0.0, 100.0, spec.decoy_pilot_rows)), 1)
    order = pd.Series(best_values).rank(method="first").to_numpy(dtype=int) - 1
    decoy = pd.Series(np.nan, index=frame.index, dtype=float)
    decoy.loc[pilot] = readings[order]

    injected = frame.copy()
    injected[spec.decoy_column] = decoy
    planted_rho = float(
        injected.loc[pilot, spec.decoy_column].corr(target, method="spearman")
    )
    return injected, PlantedRelationship(
        variables=(spec.decoy_target, spec.decoy_column),
        expected_verdict="REJECT",
        rationale=(
            f"{spec.decoy_column} is a nonsense variable recorded on a "
            f"{spec.decoy_pilot_rows}-row pilot subsample, with a planted in-sample rho "
            f"against {spec.decoy_target}. At that n the association is "
            f"indistinguishable from chance."
        ),
        in_sample_rho=planted_rho,
        n_observations=spec.decoy_pilot_rows,
    )


def _observed(frame: pd.DataFrame, x: str, y: str, rationale: str) -> PlantedRelationship:
    pair = frame[[x, y]].dropna()
    return PlantedRelationship(
        variables=(x, y),
        expected_verdict="PASS",
        rationale=rationale,
        in_sample_rho=float(pair[x].corr(pair[y], method="spearman")),
        n_observations=len(pair),
    )


def build_demo_dataset(
    output_path: Path | str,
    *,
    raw_dir: Path | str,
    spec: DemoSpec | None = None,
) -> DemoManifest:
    """Download (once), assemble, inject, and write the demo CSV. Returns the manifest.

    Guarantees: the CSV at `output_path` is exactly the frame the manifest
    describes, and rebuilding with the same spec reproduces it byte for byte.
    """
    resolved = spec if spec is not None else load_demo_spec()
    components = read_components(download_nhanes(raw_dir))
    frame = assemble_subset(components, resolved)
    frame, injected = inject_false_correlation(frame, resolved)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)

    return DemoManifest(
        source="NHANES 2017-2018 (DEMO_J, BMX_J, BPX_J, GHB_J, TCHOL_J, HDL_J)",
        spec=resolved,
        n_rows=len(frame),
        columns=[str(column) for column in frame.columns],
        expected_pass=[
            _observed(
                frame,
                "age_years",
                "systolic_bp",
                "Systolic blood pressure rises with age in adults (published NHANES finding).",
            ),
            _observed(
                frame,
                "bmi",
                "hdl_chol",
                "HDL cholesterol is lower at higher BMI (published NHANES finding).",
            ),
        ],
        injected_false=injected,
    )
