"""Which null each claim gets, which claims get none, and which rows the gate sees.

Three jobs, all trusted code that runs before any generated program (PLAN D5, D6, D6b):

  * `assign_plan` -- choose the permutation scheme that respects how the rows depend
    on each other, or refuse the claim (NOT_TESTABLE) when no valid null exists, the
    series is too short, or its differences are still too dependent to test.
  * `with_period_column` -- add the reserved `PERIOD_COLUMN`, one number per row that
    orders periods and groups rows of the same period, computed here so generated code
    never parses dates.
  * `split_rows` -- divide the table once, seeded, into exploration rows (what the
    proposer may look at) and confirmation rows (what the gate tests on). Time data
    splits by time, panels by entity, independent rows at random.

The scheme chosen here is stamped into the result by `pramana.verification.stats`, and
the executor refuses a result carrying any other scheme, so generated code cannot fall
back to a free shuffle on time-ordered data.

Owner: P.P. Satya Karthikeya
Scope: PLAN_analysis_platform.md P1
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType, PermutationScheme, TableShape
from pramana.contracts.structure import DataStructure, SplitRecord
from pramana.verification.config import DependenceConfig, VerificationConfig
from pramana.verification.stats.dependence import default_block_length, lag1_autocorrelation
from pramana.verification.stats.forecast import period_series

#: The reserved column the gate adds: a sortable number per period. No uploaded column
#: can collide with it in practice, and `with_period_column` refuses one that does.
PERIOD_COLUMN = "__pramana_period__"

_PERIOD_CODES = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}


class ForecastPlan(BaseModel):
    """What the gate fixed for one forecast claim before any held-back period is scored.

    Guarantees: frozen; `test_start_period` is the first held-back period (the earliest period
    of the confirmation rows), so no origin scores an earlier one; `min_train` is the history
    every origin has at least. The counts are the ones the plan was accepted on.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: str
    baseline: str
    aggregate: str
    horizon: int = Field(ge=1)
    season: int = Field(ge=2)
    period: str
    test_start_period: float
    min_train: int = Field(ge=2)
    max_gap_fraction: float = Field(ge=0.0)
    n_periods: int = Field(ge=1)
    n_origins: int = Field(ge=1)
    n_blocks: int = Field(ge=1)


class TestPlan(BaseModel):
    """The null one claim will be tested under, decided before code is generated.

    Guarantees: `columns` lists every structural column the program may read besides the
    claim's own; `block_length` is set exactly for `BLOCK_DIFFERENCED`.
    """

    __test__ = False  # not a pytest test class
    model_config = ConfigDict(frozen=True, extra="forbid")

    scheme: PermutationScheme
    period_column: str | None = None
    entity_column: str | None = None
    block_length: int | None = Field(default=None, ge=1)
    min_periods: int | None = Field(default=None, ge=1)
    cycle_length: int | None = Field(default=None, ge=2)
    n_periods: int | None = Field(default=None, ge=0)
    forecast: ForecastPlan | None = None

    @property
    def columns(self) -> tuple[str, ...]:
        if self.scheme is PermutationScheme.CLUSTER:
            return tuple(c for c in (self.entity_column,) if c)
        return tuple(c for c in (self.period_column, self.entity_column) if c)


FREE_PLAN = TestPlan(scheme=PermutationScheme.FREE)


def _period_values(series: pd.Series, period: str | None) -> pd.Series:
    """A float per row that orders periods; equal within one period, NaN if unknown."""
    is_date = pd.api.types.is_datetime64_any_dtype(series)
    if not is_date:
        numeric = pd.to_numeric(series, errors="coerce")
        if period not in _PERIOD_CODES or numeric.notna().sum() >= series.notna().sum() > 0:
            return numeric.round() if period == "year" else numeric
    stamps = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    periods = stamps.dt.tz_localize(None).dt.to_period(_PERIOD_CODES[period])
    return periods.map(lambda p: float(p.ordinal) if pd.notna(p) else np.nan).astype(float)


def with_period_column(frame: pd.DataFrame, structure: DataStructure) -> pd.DataFrame:
    """`frame` with `PERIOD_COLUMN` added, or unchanged for a cross-section.

    Guarantees: never modifies `frame` in place; rows in one period share one value.
    """
    if structure.shape is TableShape.CROSS_SECTION or structure.time_column is None:
        return frame
    if PERIOD_COLUMN in frame.columns:
        raise ValueError(f"the table already has a column named {PERIOD_COLUMN!r}")
    if structure.time_column not in frame.columns:
        raise ValueError(f"time column {structure.time_column!r} is not in the table")
    out = frame.copy()
    out[PERIOD_COLUMN] = _period_values(frame[structure.time_column], structure.period)
    return out


# --- the split (D5) ----------------------------------------------------------


def _digest(positions: np.ndarray) -> str:
    joined = ",".join(str(int(p)) for p in np.sort(positions))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def split_rows(
    frame: pd.DataFrame, structure: DataStructure, config: VerificationConfig
) -> tuple[np.ndarray, np.ndarray, SplitRecord]:
    """Exploration and confirmation row POSITIONS, and the record of how they were made.

    Guarantees: deterministic for the same frame, structure and config; the two sets are
    disjoint and together cover every row; time data puts the LATER periods in
    confirmation, a panel with enough entities splits whole entities, and independent
    rows split at random. Rows with no time value stay in exploration: no ordered test
    can use them.
    """
    dependence = config.dependence
    fraction = dependence.confirmation_fraction
    seed = config.statistics.seed
    n = len(frame)
    every = np.arange(n)
    rng = np.random.default_rng(seed)
    method: str
    if structure.shape is TableShape.CROSS_SECTION:
        method = "random_rows"
        confirm = np.sort(rng.permutation(n)[: int(round(n * fraction))])
    else:
        entity = structure.entity_column
        entities = (
            pd.Series(frame[entity].astype(str).where(frame[entity].notna())).dropna().unique()
            if entity
            else np.array([])
        )
        if structure.shape is TableShape.PANEL and len(entities) >= dependence.min_split_entities:
            method = "by_entity"
            chosen = set(rng.permutation(np.sort(entities))[: int(round(len(entities) * fraction))])
            confirm = every[frame[entity].astype(str).isin(chosen).to_numpy()]
        else:
            method = "by_time"
            keys = _period_values(frame[structure.time_column], structure.period)
            periods = np.sort(keys.dropna().unique())
            n_confirm = math.ceil(len(periods) * fraction) if len(periods) else 0
            # A short series would otherwise leave the gate too few periods to test a
            # trend: hold back what the gate needs while exploration keeps its minimum.
            needed = max(dependence.min_series_length.values())
            if n_confirm < needed <= len(periods) - dependence.min_exploration_periods:
                n_confirm = needed
            fraction = n_confirm / len(periods) if len(periods) else fraction
            later = set(periods[len(periods) - n_confirm :])
            confirm = every[keys.isin(later).to_numpy()]
    explore = np.setdiff1d(every, confirm)
    record = SplitRecord(
        method=method,  # type: ignore[arg-type]
        seed=seed,
        confirmation_fraction=fraction,
        n_exploration=int(explore.size),
        n_confirmation=int(confirm.size),
        confirmation_digest=_digest(confirm),
    )
    return explore, confirm, record


def exploration_frame(frame: pd.DataFrame, structure: DataStructure, config: VerificationConfig):
    """The rows the proposer may look at. Never contains a confirmation row."""
    explore, _, record = split_rows(frame, structure, config)
    return frame.iloc[explore].reset_index(drop=True), record


def confirmation_frame(frame: pd.DataFrame, structure: DataStructure, config: VerificationConfig):
    """The rows the gate tests on, and the split record that says so."""
    _, confirm, record = split_rows(frame, structure, config)
    return frame.iloc[confirm].reset_index(drop=True), record


# --- scheme assignment and the refusal screens (D6, D6b) ------------------------


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce")


def _period_series(frame: pd.DataFrame, column: str) -> pd.Series:
    """Mean of `column` per period, in period order: what an ordered test runs on."""
    data = pd.DataFrame({"p": frame[PERIOD_COLUMN], "v": _numeric(frame, column)}).dropna()
    return data.groupby("p")["v"].mean().sort_index()


def _block_length(dependence: DependenceConfig, n_steps: int) -> int:
    if dependence.block_length == "auto":
        return default_block_length(n_steps)
    return max(1, min(int(dependence.block_length), n_steps))


def _dependent_differences(series: pd.Series, dependence: DependenceConfig) -> float | None:
    """The lag-1 autocorrelation of the differences if it is above the cutoff, else None."""
    r1 = lag1_autocorrelation(np.diff(series.to_numpy(dtype=float)))
    return r1 if r1 > dependence.max_diff_autocorrelation else None


def _ordered_plan(
    candidate: CandidateInsight,
    frame: pd.DataFrame,
    dependence: DependenceConfig,
    columns: list[str],
) -> TestPlan | str:
    """A BLOCK_DIFFERENCED plan on the per-period series of `columns`, or a refusal."""
    kind = candidate.claim_type.value
    minimum = dependence.min_series_length[kind]
    if len(columns) == 2:
        joint = (
            pd.DataFrame(
                {
                    "p": frame[PERIOD_COLUMN],
                    "x": _numeric(frame, columns[0]),
                    "y": _numeric(frame, columns[1]),
                }
            )
            .dropna()
            .groupby("p")
            .mean()
            .sort_index()
        )
        series = [joint["x"], joint["y"]]
    else:
        series = [_period_series(frame, columns[0])]
    n_periods = len(series[0])
    if n_periods < minimum:
        return (
            f"too few periods to test: {n_periods} periods in the confirmation rows, and a "
            f"{kind} claim on time-ordered data needs at least {minimum} "
            f"(verification.yaml dependence.min_series_length.{kind}). The figures "
            f"computed on the whole table still describe what changed."
        )
    for name, values in zip(columns, series, strict=True):
        r1 = _dependent_differences(values, dependence)
        if r1 is not None:
            return (
                f"the period-to-period changes of {name} are still strongly dependent "
                f"(lag-1 autocorrelation {r1:.2f} > "
                f"{dependence.max_diff_autocorrelation}), so no valid null can be built "
                f"for it; the claim was not tested"
            )
    return TestPlan(
        scheme=PermutationScheme.BLOCK_DIFFERENCED,
        period_column=PERIOD_COLUMN,
        block_length=_block_length(dependence, n_periods - 1),
        min_periods=minimum,
        n_periods=n_periods,
    )


def _movable_rows(frame: pd.DataFrame, columns: list[str]) -> int:
    rows = pd.DataFrame({c: frame[c] for c in [*columns, PERIOD_COLUMN]}).dropna()
    counts = rows[PERIOD_COLUMN].value_counts()
    return int(counts[counts >= 2].sum())


_CYCLES = {"month": 12, "quarter": 4}


def _time_claim_plan(
    candidate: CandidateInsight,
    frame: pd.DataFrame,
    structure: DataStructure,
    config: VerificationConfig,
) -> TestPlan | str:
    """Plans for T4 (period change) and T6 (seasonality), or the refusal."""
    var_x, var_y = (candidate.variables + [None, None])[:2]
    time, entity = structure.time_column, structure.entity_column
    if structure.shape is TableShape.CROSS_SECTION or time is None:
        return "the table has no time axis, so there is no period to compare"
    if var_x != time:
        return f"a {candidate.claim_type.value} claim is about the time axis {time!r}"
    rows = pd.DataFrame({"p": frame[PERIOD_COLUMN], "v": _numeric(frame, var_y)})
    if entity:
        rows["e"] = frame[entity].astype(str)
    rows = rows.dropna()
    if candidate.claim_type is ClaimType.SEASONALITY:
        cycle = _CYCLES.get(structure.period or "")
        if cycle is None:
            return "seasonality is tested on monthly or quarterly data only"
        ordinals = np.round(np.sort(rows["p"].unique())).astype(int)
        positions = pd.Series(ordinals % cycle).value_counts()
        if len(positions) < cycle or int(positions.min()) < 2:
            return (
                "too few periods to test: every month (or quarter) needs at least two years "
                "of values in the confirmation rows"
            )
        return TestPlan(
            scheme=PermutationScheme.STRATIFIED, period_column=PERIOD_COLUMN, cycle_length=cycle
        )
    periods = np.sort(rows["p"].unique())
    if len(periods) < 2:
        return "a change needs at least two periods in the confirmation rows"
    last = rows[rows["p"].isin(periods[-2:])]
    if structure.shape is TableShape.TIME_SERIES:
        return (
            "one value per period cannot be tested as a change between two periods; the "
            "change itself is in the report"
        )
    if entity and structure.shape is TableShape.PANEL:
        both = last.groupby("e")["p"].nunique()
        n_pairs = int((both == 2).sum())
        if n_pairs < config.dependence.min_clusters:
            return (
                f"{n_pairs} entities have values in both of the last two periods; at least "
                f"{config.dependence.min_clusters} are needed (dependence.min_clusters)"
            )
        return TestPlan(
            scheme=PermutationScheme.PAIRED, period_column=PERIOD_COLUMN, entity_column=entity
        )
    if last.groupby("p").size().min() < 2 or len(last) < config.statistics.min_observations:
        return "too few rows in the last two periods to compare them"
    return TestPlan(scheme=PermutationScheme.FREE, period_column=PERIOD_COLUMN)


def _forecast_plan(
    candidate: CandidateInsight,
    frame: pd.DataFrame,
    structure: DataStructure,
    config: VerificationConfig,
    history: pd.DataFrame | None,
    split: SplitRecord | None,
) -> TestPlan | str:
    """The plan for a forecast claim, or the plain reason it cannot be tested.

    `frame` is the held-back (confirmation) rows with `PERIOD_COLUMN`; `history` is the earlier
    rows the method may be fitted on, with the same column. Guarantees: refuses unless the
    table has a time axis, was split by time, has a period type with a seasonal length in the
    config, and the held-back periods give at least `forecast.min_origins` origins in at least
    `forecast.min_blocks` blocks of one horizon each.
    """
    settings = config.forecast
    spec = candidate.forecast
    if not config.claims.forecast_enabled:
        return "forecast claims are switched off (claims.forecast_enabled is false)"
    if spec is None:
        return "a forecast claim must name its horizon and method; this one names neither"
    time, target = structure.time_column, candidate.variables[1]
    if structure.shape is TableShape.CROSS_SECTION or time is None:
        return "the table has no time axis, so there is nothing to forecast"
    if candidate.variables[0] != time:
        return f"a forecast claim starts with the time axis {time!r}"
    if target not in frame.columns or pd.api.types.is_bool_dtype(frame[target]):
        return f"{target!r} is not a numeric column"
    if split is None or split.method != "by_time":
        how = "no split" if split is None else f"a split by {split.method.replace('_', ' ')}"
        return (
            f"a forecast is scored on a later stretch of time held back from the proposer; this "
            f"run used {how}, so no period is both unseen and later than the history"
        )
    period = structure.period or ""
    season = settings.seasonal_length.get(period)
    if season is None:
        return (
            f"forecast claims are tested on {' or '.join(sorted(settings.seasonal_length))} data "
            f"only; this table's period is {period or 'unknown'}"
        )
    if spec.horizon > settings.max_horizon:
        return f"a horizon of {spec.horizon} periods exceeds the limit of {settings.max_horizon}"
    if history is None or history.empty:
        return (
            "the earlier periods are needed to fit the method before each origin, and none "
            "were given to the gate"
        )
    both = pd.concat([history, frame], ignore_index=True)
    held = frame[PERIOD_COLUMN].dropna()
    if held.empty:
        return "the held-back rows have no period values"
    test_start = float(held.min())
    rows = pd.DataFrame({"p": both[PERIOD_COLUMN], "v": _numeric(both, target)}).dropna()
    try:
        series = period_series(
            rows["p"],
            rows["v"],
            aggregate=spec.aggregate,
            test_start_period=test_start,
            max_gap_fraction=settings.max_gap_fraction,
        )
    except ValueError as error:
        return f"the series could not be laid out for a backtest: {error}"
    min_train = max(settings.min_cycles * season, settings.min_train_floor)
    first = max(series.test_start, min_train)
    n_origins = series.values.size - spec.horizon + 1 - first
    n_blocks = math.ceil(max(n_origins, 0) / spec.horizon)
    if n_origins < settings.min_origins or n_blocks < settings.min_blocks:
        return (
            f"too few backtest origins: the held-back periods give {max(n_origins, 0)} origins "
            f"({n_blocks} blocks of {spec.horizon}), and a forecast claim needs at least "
            f"{settings.min_origins} origins in {settings.min_blocks} blocks "
            f"(verification.yaml forecast.min_origins, forecast.min_blocks); a shorter backtest "
            f"cannot produce a p-value small enough to pass"
        )
    lag = season if spec.baseline == "seasonal_naive" else 1
    before = series.values[:first]
    if not float(np.mean(np.abs(before[lag:] - before[:-lag]))) > 0.0:
        return f"{target!r} is constant before the first origin, so errors cannot be scaled"
    return TestPlan(
        scheme=PermutationScheme.BLOCK_SIGN_FLIP,
        period_column=PERIOD_COLUMN,
        block_length=spec.horizon,
        min_periods=min_train,
        n_periods=int(series.values.size),
        forecast=ForecastPlan(
            method=spec.method,
            baseline=spec.baseline,
            aggregate=spec.aggregate,
            horizon=spec.horizon,
            season=season,
            period=period,
            test_start_period=test_start,
            min_train=min_train,
            max_gap_fraction=settings.max_gap_fraction,
            n_periods=int(series.values.size),
            n_origins=int(n_origins),
            n_blocks=int(n_blocks),
        ),
    )


def assign_plan(
    candidate: CandidateInsight,
    frame: pd.DataFrame,
    structure: DataStructure,
    config: VerificationConfig,
    *,
    history: pd.DataFrame | None = None,
    split: SplitRecord | None = None,
) -> TestPlan | str:
    """The null `candidate` is tested under on `frame`, or the reason it cannot be.

    `frame` is the confirmation rows WITH `PERIOD_COLUMN` (see `with_period_column`).
    Guarantees: a cross-section always gets `FREE`; time-ordered and grouped tables never
    do; a returned string is a refusal written for the user, and the claim then never
    enters the BH family.
    """
    if candidate.claim_type is ClaimType.FORECAST:
        return _forecast_plan(candidate, frame, structure, config, history, split)
    if candidate.claim_type in (ClaimType.PERIOD_CHANGE, ClaimType.SEASONALITY):
        return _time_claim_plan(candidate, frame, structure, config)
    if structure.shape is TableShape.CROSS_SECTION:
        return FREE_PLAN
    dependence = config.dependence
    kind = candidate.claim_type
    var_x, var_y = (candidate.variables + [None, None])[:2]
    time, entity = structure.time_column, structure.entity_column

    if kind is ClaimType.TREND:
        if var_x != time:
            return (
                f"a trend on this table is tested against its time axis {time!r}; "
                f"{var_x!r} is not it"
            )
        return _ordered_plan(candidate, frame, dependence, [var_y])

    if time in (var_x, var_y):
        return f"{time!r} is the table's time axis; a claim about it is a trend claim"

    if kind is ClaimType.CORRELATION:
        if structure.shape is TableShape.TIME_SERIES:
            return _ordered_plan(candidate, frame, dependence, [var_x, var_y])
        if _movable_rows(frame, [var_x, var_y]) < config.statistics.min_observations:
            return (
                "too few rows share a period with another row to compare within periods; "
                "the claim was not tested"
            )
        return TestPlan(scheme=PermutationScheme.STRATIFIED, period_column=PERIOD_COLUMN)

    if kind is ClaimType.GROUP_DIFFERENCE:
        if structure.shape is TableShape.TIME_SERIES:
            return (
                "a one-row-per-period table has no valid null for a group comparison; "
                "the claim was not tested"
            )
        if var_x == entity:
            return (
                f"comparing the {entity!r} entities with each other needs a null over whole "
                f"series, which the gate does not have yet; the claim was not tested"
            )
        rows = frame[[var_x, var_y, *([entity] if entity else [])]].dropna()
        if entity and (rows.groupby(entity)[var_x].nunique() <= 1).all():
            n_entities = int(rows[entity].nunique())
            if n_entities < dependence.min_clusters:
                return (
                    f"{var_x!r} is fixed for each {entity!r}, so the comparison is between "
                    f"{n_entities} entities in the confirmation rows; at least "
                    f"{dependence.min_clusters} are needed (dependence.min_clusters)"
                )
            return TestPlan(scheme=PermutationScheme.CLUSTER, entity_column=entity)
        mixed = (
            frame[[var_x, PERIOD_COLUMN]].dropna().groupby(PERIOD_COLUMN)[var_x].nunique() >= 2
        ).sum()
        if mixed == 0:
            return (
                f"no period holds two different levels of {var_x!r}, so the groups cannot "
                f"be compared within periods; the claim was not tested"
            )
        return TestPlan(scheme=PermutationScheme.STRATIFIED, period_column=PERIOD_COLUMN)

    return FREE_PLAN  # other claim types are refused by the admissibility screen
