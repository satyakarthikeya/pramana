"""Planted-dataset builder: a pre-shuffle extract in, a labelled benchmark dataset out.

SPEC.md 2, in order:

1. Take a real extract -- real column names, dtypes, missingness and marginals.
2. **Independently shuffle every column.** Every real association is destroyed and every
   marginal is left exactly as it was, so the frame is pure null by construction.
3. **Inject `k` relationships** of known type, magnitude and direction from the logged
   schedule (`configs/evaluation.yaml`).
4. Write the ground-truth table: every injected pair with its type and magnitude, every
   other pair labelled null.

How an effect is injected
-------------------------
The injected column is not overwritten with synthetic numbers. Its values at the rows
that take part in the test are PERMUTED so that they line up with a latent variable
(rank-remapping), which keeps the column's marginal distribution and missingness
exactly. The mixing weight is then BISECTED until the vetted effect size from
`pramana.verification.stats` -- computed on pair-complete rows exactly as the
falsification templates compute it -- equals the target. A closed-form inversion
(`asin`, `Phi^-1`) would drift once ties and pairwise missingness enter; calibrating to
the realised value keeps the claim "this effect sits 1.25x above the floor" true in fact.
The target, the realised value and the floor used are all recorded.

Why injections use disjoint columns
-----------------------------------
Two injections sharing a column would make the pairs between them transitively
associated, and those pairs would still be labelled null. The truth table would then be
wrong in a way no system could be blamed for, so the builder refuses to share.

Effect sizes are multiples of the gate's own floor, read from the verification config at
build time, so the schedule keeps straddling the boundary when the bands are
recalibrated (`docs/OPEN_ISSUES.md` 11).

Seam: this module imports `pramana.verification.stats` (the vetted effect-size library)
and `VerificationConfig`, nothing else from another member's modules.

Owner: P.P. Satya Karthikeya
Scope: src/pramana/evaluation/SPEC.md 2
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import combinations
from statistics import NormalDist
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from pramana.contracts.enums import EffectMetric
from pramana.evaluation.config import (
    EffectLevel,
    EvaluationConfig,
    ExtractShape,
    PlantedConfig,
    RelationshipType,
    SignDirection,
)
from pramana.verification.config import VerificationConfig
from pramana.verification.stats import cliffs_delta, kendall_tau_b, spearman_rho

#: The gating metric each injected relationship type is calibrated to and judged on.
METRIC_BY_TYPE: dict[RelationshipType, EffectMetric] = {
    RelationshipType.MONOTONIC: EffectMetric.SPEARMAN_RHO,
    RelationshipType.SHIFT: EffectMetric.CLIFFS_DELTA,
    RelationshipType.TREND: EffectMetric.KENDALL_TAU_B,
}

_BISECTION_STEPS = 60
_SHIFT_SEARCH_LIMIT = 12.0  # latent shift, in standard-normal units: delta ~ 1 well before this


class CalibrationError(RuntimeError):
    """The requested effect cannot be injected into this extract within tolerance."""


class ScheduledInjection(BaseModel):
    """One entry of the logged schedule: what to inject, before any column is chosen."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relationship_type: RelationshipType
    direction: SignDirection
    effect_level: str
    multiplier_of_floor: float


class TruthRow(BaseModel):
    """One column pair of the ground-truth table.

    `label` is `injected` or `null`. For an injected pair, `direction` is the sign of the
    relationship; for a shift it is relative to `reference_group` (positive means the
    reference group sits HIGHER). `levels` and `reference_group` are stored in the
    string form the falsification template builds (`astype(str)`), because that is the
    form a candidate's `reference_group` has to match.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    var_a: str
    var_b: str
    label: Literal["injected", "null"]
    relationship_type: RelationshipType | None = None
    effect_level: str | None = None
    effect_metric: EffectMetric | None = None
    direction: SignDirection | None = None
    multiplier_of_floor: float | None = None
    floor: float | None = None
    target_effect: float | None = None
    realised_effect: float | None = None
    group_column: str | None = None
    value_column: str | None = None
    reference_group: str | None = None
    levels: list[str] | None = None


class GroundTruth(BaseModel):
    """The complete label set for one dataset, plus how it was built."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str
    dataset_index: int
    base_seed: int
    build_seed: int
    k: int = Field(ge=0)
    schedule: list[ScheduledInjection]
    floors: dict[str, float] = Field(default_factory=dict)
    calibration_tolerance: float | None = None
    frame_digest: str
    rows: list[TruthRow]


@dataclass(frozen=True)
class PlantedDataset:
    """A built benchmark dataset: the frame systems see, and the truth they are scored on."""

    frame: pd.DataFrame
    truth: GroundTruth


# --- schedule ---------------------------------------------------------------------


def dataset_seed(config: PlantedConfig, dataset_index: int) -> int:
    """The build seed of dataset `dataset_index`: a pure function of `(base_seed, index)`."""
    sequence = np.random.SeedSequence([config.base_seed, dataset_index])
    return int(sequence.generate_state(1)[0])


def k_for(config: PlantedConfig, dataset_index: int) -> int:
    """How many relationships dataset `dataset_index` gets, from the cycled schedule."""
    return config.k_per_dataset[dataset_index % len(config.k_per_dataset)]


def scheduled_injections(
    config: PlantedConfig, dataset_index: int, k: int
) -> list[ScheduledInjection]:
    """The first `k` schedule entries for a dataset. Deterministic; no randomness.

    Types cycle from the start so every dataset with k >= 3 carries all three shapes;
    direction and effect level are offset by the dataset index so levels and signs mix
    across the benchmark rather than repeating per dataset.
    """
    out: list[ScheduledInjection] = []
    for j in range(k):
        level: EffectLevel = config.effect_levels[(dataset_index + j) % len(config.effect_levels)]
        out.append(
            ScheduledInjection(
                relationship_type=config.relationship_cycle[j % len(config.relationship_cycle)],
                direction=config.direction_cycle[(dataset_index + j) % len(config.direction_cycle)],
                effect_level=level.name,
                multiplier_of_floor=level.multiplier_of_floor,
            )
        )
    return out


# --- helpers ----------------------------------------------------------------------


def _normal_scores(values: np.ndarray) -> np.ndarray:
    """Van der Waerden scores: ranks (ties averaged) mapped to standard-normal quantiles."""
    n = values.size
    ranks = pd.Series(values).rank(method="average").to_numpy()
    inverse = NormalDist().inv_cdf
    return np.array([inverse((r - 0.5) / n) for r in ranks])


def _remap(sorted_values: np.ndarray, latent: np.ndarray) -> np.ndarray:
    """Place `sorted_values` so their order follows `latent`: a permutation, so the
    marginal of the original values is preserved exactly."""
    order = np.argsort(latent, kind="stable")
    out = np.empty_like(sorted_values)
    out[order] = sorted_values
    return out


def _bisect(
    realised: Callable[[float], float], lo: float, hi: float, target: float, tolerance: float
) -> float:
    """Find the parameter whose realised effect equals `target` (effect increasing in it)."""
    best, best_gap = lo, math.inf
    for _ in range(_BISECTION_STEPS):
        mid = (lo + hi) / 2.0
        gap = realised(mid) - target
        if abs(gap) < best_gap:
            best, best_gap = mid, abs(gap)
        if abs(gap) <= tolerance / 4.0:
            break
        if gap < 0:
            lo = mid
        else:
            hi = mid
    if best_gap > tolerance:
        raise CalibrationError(
            f"could not reach target effect {target:.4f} within {tolerance}; closest was "
            f"{target + best_gap:.4f} (ties or missingness may cap the achievable effect)"
        )
    return best


def _inject_numeric_pair(
    frame: pd.DataFrame,
    x_col: str,
    y_col: str,
    sign: float,
    target: float,
    metric: Callable[[np.ndarray, np.ndarray], float],
    tolerance: float,
    rng: np.random.Generator,
) -> float:
    """Rank-remap `y_col` against `x_col` until `metric` hits `sign * target`. Returns the
    realised signed effect, computed on pair-complete rows as the template computes it."""
    pair = frame[[x_col, y_col]].apply(pd.to_numeric, errors="coerce")
    rows = pair.notna().all(axis=1).to_numpy()
    x = pair.loc[rows, x_col].to_numpy(dtype=float)
    y_sorted = np.sort(pair.loc[rows, y_col].to_numpy(dtype=float))
    z = _normal_scores(x)
    noise = rng.standard_normal(x.size)

    def build(weight: float) -> np.ndarray:
        latent = sign * weight * z + math.sqrt(max(0.0, 1.0 - weight**2)) * noise
        return _remap(y_sorted, latent)

    weight = _bisect(lambda w: sign * metric(x, build(w)), 0.0, 1.0, target, tolerance)
    new_y = build(weight)
    values = frame[y_col].to_numpy(dtype=float, na_value=np.nan).copy()
    values[rows] = new_y
    frame[y_col] = values
    return float(metric(x, new_y))


def _inject_shift(
    frame: pd.DataFrame,
    group_col: str,
    y_col: str,
    reference: str,
    sign: float,
    target: float,
    tolerance: float,
) -> float:
    """Shift `y_col` between the levels of `group_col` until Cliff's delta (reference group
    first) hits `sign * target`. Returns the realised signed delta."""
    y_numeric = pd.to_numeric(frame[y_col], errors="coerce")
    rows = (frame[group_col].notna() & y_numeric.notna()).to_numpy()
    labels = frame.loc[rows, group_col].astype(str).to_numpy()
    is_reference = labels == reference
    y_sorted = np.sort(y_numeric[rows].to_numpy(dtype=float))
    base = _normal_scores(y_numeric[rows].to_numpy(dtype=float))

    def build(shift: float) -> np.ndarray:
        return _remap(y_sorted, base + sign * shift * is_reference)

    def delta(values: np.ndarray) -> float:
        return float(cliffs_delta(values[is_reference], values[~is_reference]))

    shift = _bisect(lambda s: sign * delta(build(s)), 0.0, _SHIFT_SEARCH_LIMIT, target, tolerance)
    new_y = build(shift)
    values = y_numeric.to_numpy(dtype=float, na_value=np.nan).copy()
    values[rows] = new_y
    frame[y_col] = values
    return delta(new_y)


def _frame_digest(frame: pd.DataFrame) -> str:
    return hashlib.sha256(frame.to_csv(index=False).encode("utf-8")).hexdigest()


def _classify_columns(
    frame: pd.DataFrame, ordinal_columns: Sequence[str]
) -> tuple[list[str], list[str], list[str]]:
    """(numeric, binary, ordinal) column pools, in frame order."""
    ordinal = [c for c in frame.columns if c in set(ordinal_columns)]
    binary = [
        c for c in frame.columns if c not in ordinal and frame[c].dropna().nunique() == 2
    ]
    numeric = [
        c
        for c in frame.columns
        if c not in ordinal
        and c not in binary
        and pd.api.types.is_numeric_dtype(frame[c])
        and frame[c].dropna().nunique() > 2
    ]
    return numeric, binary, ordinal


def _take(pool: list[str], rng: np.random.Generator, what: str) -> str:
    if not pool:
        raise CalibrationError(f"no unused {what} column left to inject into; lower k")
    return pool.pop(int(rng.integers(len(pool))))


# --- the builder ------------------------------------------------------------------


def build_planted_dataset(
    extract: pd.DataFrame,
    *,
    dataset_id: str,
    dataset_index: int,
    config: EvaluationConfig,
    verification: VerificationConfig,
    ordinal_columns: Sequence[str],
    k: int | None = None,
) -> PlantedDataset:
    """Build one labelled benchmark dataset from a pre-shuffle extract.

    Guarantees:

    * **Pure null before injection.** Every column is shuffled with its own seeded
      stream, so no pair carries a real association and every marginal and missingness
      rate is exactly the extract's.
    * **Complete labels.** `truth.rows` holds every unordered column pair exactly once.
    * **Calibrated.** Each injected effect's realised value is within
      `calibration_tolerance` of `multiplier_of_floor * floor`, floors read from
      `verification` now, not copied; otherwise `CalibrationError`.
    * **Reproducible.** The same extract, config and index give a byte-identical frame
      and truth. `k` defaults to the schedule's value for `dataset_index`.
    """
    planted = config.planted
    k = k_for(planted, dataset_index) if k is None else k
    build_seed = dataset_seed(planted, dataset_index)
    schedule = scheduled_injections(planted, dataset_index, k)

    frame = extract.reset_index(drop=True).copy()
    for position, column in enumerate(frame.columns):
        stream = np.random.default_rng(np.random.SeedSequence([build_seed, 0, position]))
        permutation = stream.permutation(len(frame))
        frame[column] = frame[column].iloc[permutation].reset_index(drop=True)

    numeric, binary, ordinal = _classify_columns(frame, ordinal_columns)
    chooser = np.random.default_rng(np.random.SeedSequence([build_seed, 1]))
    noise_stream = np.random.default_rng(np.random.SeedSequence([build_seed, 2]))
    tolerance = planted.calibration_tolerance

    injected: dict[frozenset[str], TruthRow] = {}
    for entry in schedule:
        metric = METRIC_BY_TYPE[entry.relationship_type]
        floor = verification.evidence.threshold_for(metric).min
        target = entry.multiplier_of_floor * floor
        sign = 1.0 if entry.direction is SignDirection.POSITIVE else -1.0
        common = {
            "label": "injected",
            "relationship_type": entry.relationship_type,
            "effect_level": entry.effect_level,
            "effect_metric": metric,
            "direction": entry.direction,
            "multiplier_of_floor": entry.multiplier_of_floor,
            "floor": floor,
            "target_effect": target,
        }
        if entry.relationship_type is RelationshipType.SHIFT:
            group_col = _take(binary, chooser, "binary categorical")
            value_col = _take(numeric, chooser, "numeric")
            levels = sorted(
                frame.loc[frame[value_col].notna(), group_col].dropna().astype(str).unique()
            )
            realised = _inject_shift(
                frame, group_col, value_col, levels[0], sign, target, tolerance
            )
            row = TruthRow(
                var_a=group_col, var_b=value_col, group_column=group_col,
                value_column=value_col, reference_group=levels[0], levels=levels,
                realised_effect=realised, **common,
            )
            pair = (group_col, value_col)
        else:
            if entry.relationship_type is RelationshipType.TREND:
                x_col = _take(ordinal, chooser, "ordinal/time")
                metric_fn = kendall_tau_b
            else:
                x_col = _take(numeric, chooser, "numeric")
                metric_fn = spearman_rho
            y_col = _take(numeric, chooser, "numeric")
            realised = _inject_numeric_pair(
                frame, x_col, y_col, sign, target, metric_fn, tolerance, noise_stream
            )
            row = TruthRow(var_a=x_col, var_b=y_col, realised_effect=realised, **common)
            pair = (x_col, y_col)
        injected[frozenset(pair)] = row

    rows: list[TruthRow] = []
    for a, b in combinations(frame.columns, 2):
        found = injected.get(frozenset((a, b)))
        rows.append(found if found is not None else TruthRow(var_a=a, var_b=b, label="null"))

    truth = GroundTruth(
        dataset_id=dataset_id,
        dataset_index=dataset_index,
        base_seed=planted.base_seed,
        build_seed=build_seed,
        k=k,
        schedule=schedule,
        floors={
            m.value: verification.evidence.threshold_for(m).min for m in METRIC_BY_TYPE.values()
        },
        calibration_tolerance=tolerance,
        frame_digest=_frame_digest(frame),
        rows=rows,
    )
    return PlantedDataset(frame=frame, truth=truth)


# --- a stand-in extract -------------------------------------------------------------


def synthetic_extract(shape: ExtractShape, seed: int) -> tuple[pd.DataFrame, list[str]]:
    """A benchmark-sized stand-in for a real pre-shuffle extract, and its ordinal columns.

    NOT benchmark data: the real extracts come from the benchmark curation (SPEC.md 6).
    It exists so the builder, the tests and the cost measurement run at the right shape
    (rows, column mix, missingness, ties) without a dataset in the repo (AGENTS.md 6).
    The numeric columns share a latent factor, so shuffling has real associations to
    destroy.
    """
    rng = np.random.default_rng(seed)
    n = shape.n_rows
    shared = rng.standard_normal(n)
    data: dict[str, np.ndarray | list] = {}
    for i in range(shape.n_numeric):
        column = 0.6 * shared + rng.standard_normal(n)
        column = np.exp(0.5 * column) if i % 3 == 2 else column
        column = np.where(rng.random(n) < 0.05, np.nan, column)
        data[f"num_{i}"] = column
    for i in range(shape.n_binary_categorical):
        if i % 2 == 0:  # float-coded like NHANES sex, with missing values
            coded = np.where(rng.random(n) < 0.5, 1.0, 2.0)
            data[f"bin_{i}"] = np.where(rng.random(n) < 0.02, np.nan, coded)
        else:
            data[f"bin_{i}"] = rng.choice(["no", "yes"], size=n)
    for i in range(shape.n_multilevel_categorical):
        data[f"cat_{i}"] = rng.choice(["a", "b", "c", "d"], size=n)
    ordinal: list[str] = []
    for i in range(shape.n_ordinal):
        data[f"ord_{i}"] = rng.integers(0, 12, size=n)
        ordinal.append(f"ord_{i}")
    return pd.DataFrame(data), ordinal
