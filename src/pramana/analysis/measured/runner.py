"""The Measured tier's entry point: which analyses run, in what order, within what budget.

Guarantees: deterministic for the same table, config and requests (every seed comes from
config); each analysis runs on its own, so one that raises becomes a visible "not run"
item with a fixed message (the exception text is logged, never shown); no analysis starts
after the time budget; a table above `max_rows` is sampled once with the logged seed
(forecasts use every row); nothing here calls a model, and nothing here reaches the
gateway, the proposer or memory.

Default plan when no request is given (the P4 planner will send `MeasuredRequest`s):
  target      the numeric column most connected to the other numeric columns (mean
              absolute Spearman correlation, ties by column order), chosen among the
              columns whose sector role is one of the pack's measures, else among columns
              with any other sector role, else among all; identifiers, the time axis, the
              entity and survey weights are never targets. A table with a time axis and a
              single numeric column still gets a forecast of that column;
  M1          regression on that target;  M2  classification on the first label column
              with 2..max_class_levels groups;  M4 segments and M5 anomalies on the numeric
              columns;  M6 forecast of the target when the table has a time axis;  M7 a
              threshold search on M1's most important numeric column (only when M1 beat its
              baseline).  M3 runs only when requested (it needs named controls).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Collection

import pandas as pd

from pramana.analysis.measured.adjusted import run_adjusted
from pramana.analysis.measured.anomalies import run_anomalies
from pramana.analysis.measured.common import not_run
from pramana.analysis.measured.config import MeasuredConfig, load_measured_config
from pramana.analysis.measured.drivers import run_driver
from pramana.analysis.measured.forecast import run_forecast
from pramana.analysis.measured.models import (
    MEASURED_VERSION,
    Exclusion,
    MeasuredAnalysis,
    MeasuredItem,
    MeasuredRequest,
)
from pramana.analysis.measured.prep import Aggregated, aggregate_transactions, num
from pramana.analysis.measured.segments import numeric_columns, run_segments
from pramana.analysis.measured.threshold import run_threshold
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile
from pramana.analysis.shape import ShapeProfile
from pramana.common.logging import get_logger

logger = get_logger(component="measured")

_FAILED = "This analysis could not be completed on this table."
_OUT_OF_TIME = "The time budget ran out before this analysis could start."
_NON_TARGET_ROLES = {"entity", "survey_weight"}
#: Tasks that fit rows and so need rows that can be held out whole.
_ROW_LEVEL = {"driver_regression", "driver_classification", "adjusted_association", "threshold"}


def pick_target(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    config: MeasuredConfig,
    roles: dict[str, str],
    measure_roles: Collection[str] = (),
) -> str | None:
    """The default numeric target; see the module docstring for the rule."""
    columns = numeric_columns(frame, schema, shape, config, roles=roles)
    if len(columns) < 2:
        return None
    measures = [c for c in columns if roles.get(c) in measure_roles]
    with_role = [c for c in columns if roles.get(c) not in _NON_TARGET_ROLES and c in roles]
    pool = measures or with_role or columns
    data = pd.DataFrame({c: num(frame[c]) for c in columns})
    corr = data.corr(method="spearman").abs()
    connected = {c: float((corr.loc[c].drop(c)).mean()) for c in pool}
    best = max(connected.values())
    return next(c for c in pool if connected[c] == best)


def pick_forecast_target(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    config: MeasuredConfig,
    roles: dict[str, str],
    measure_roles: Collection[str] = (),
) -> str | None:
    """The column to forecast: the first sector measure, else the first numeric column."""
    columns = numeric_columns(frame, schema, shape, config, roles=roles)
    measures = [c for c in columns if roles.get(c) in measure_roles]
    return (measures or columns or [None])[0]


def pick_class_target(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    config: MeasuredConfig,
    roles: dict[str, str],
    avoid: str | None,
) -> str | None:
    """The first label column with a small number of groups, none of them rare."""
    for name, profile in schema.columns.items():
        if profile.role is not ColumnRole.CATEGORICAL or name not in frame.columns:
            continue
        if name in {avoid, shape.time_column, shape.entity_column}:
            continue
        if roles.get(name) in _NON_TARGET_ROLES:
            continue
        counts = frame[name].dropna().astype(str).value_counts()
        if 2 <= len(counts) <= config.max_class_levels and int(counts.min()) >= (
            config.min_class_rows
        ):
            return name
    return None


def _execute(
    request: MeasuredRequest,
    *,
    frame: pd.DataFrame,
    full: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    config: MeasuredConfig,
    roles: dict[str, str],
    additive: bool,
    deadline: float,
    rolled_up: Aggregated | None = None,
) -> MeasuredItem:
    task, target = request.task, request.target
    if rolled_up is not None and task in _ROW_LEVEL:
        item = _execute(
            request,
            frame=rolled_up.frame,
            full=full,
            schema=rolled_up.schema,
            shape=rolled_up.shape,
            config=config,
            roles=roles,
            additive=additive,
            deadline=deadline,
        )
        if item.status == "ok" and item.sentence:
            return item.model_copy(update={"sentence": f"{item.sentence} {rolled_up.note}"})
        return item
    features = request.features or None
    if task in {"driver_regression", "driver_classification"}:
        if target is None:
            return not_run(task, "A target column is needed.")
        return run_driver(
            frame,
            schema,
            shape,
            task="regression" if task == "driver_regression" else "classification",
            target=target,
            config=config,
            features=features,
            roles=roles,
            deadline=deadline,
        )
    if task == "adjusted_association":
        if target is None or not request.features:
            return not_run(task, "A target and the column to test are needed.", target)
        return run_adjusted(
            frame,
            schema,
            shape,
            target=target,
            variable=request.features[0],
            controls=request.controls,
            config=config,
            roles=roles,
        )
    if task == "segments":
        return run_segments(frame, schema, shape, config=config, columns=features, roles=roles)
    if task == "anomalies":
        return run_anomalies(frame, schema, shape, config=config, columns=features, roles=roles)
    if task == "forecast":
        if target is None:
            return not_run(task, "A target column is needed.")
        return run_forecast(full, schema, shape, target=target, config=config, additive=additive)
    if target is None or not request.features:
        return not_run(task, "A target and the column to search are needed.", target)
    return run_threshold(
        frame,
        schema,
        shape,
        target=target,
        variable=request.features[0],
        config=config,
        roles=roles,
    )


def compute_measured(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    *,
    config: MeasuredConfig | None = None,
    roles: dict[str, str] | None = None,
    requests: list[MeasuredRequest] | None = None,
    additive: bool = True,
    measure_roles: Collection[str] = (),
) -> MeasuredAnalysis:
    """Run the Measured tier on a cleaned table (the default plan, or the given requests).

    `measure_roles` are the sector pack's measure roles, used to choose the default target.
    """
    config = config or load_measured_config()
    roles = roles or {}
    started = time.monotonic()
    deadline = started + config.time_budget_seconds
    sampled = None
    work = frame
    if len(frame) > config.max_rows:
        work = frame.sample(n=config.max_rows, random_state=config.seed).sort_index()
        sampled = config.max_rows

    items: list[MeasuredItem] = []
    rolled: list[Aggregated | None] = []

    def rolled_up() -> Aggregated | None:
        if not rolled:
            try:
                rolled.append(aggregate_transactions(work, schema, shape, roles))
            except Exception:
                logger.exception("measured_rollup_failed")
                rolled.append(None)
        return rolled[0]

    def attempt(request: MeasuredRequest) -> MeasuredItem:
        if time.monotonic() > deadline:
            return not_run(request.task, _OUT_OF_TIME, request.target)
        try:
            return _execute(
                request,
                frame=work,
                full=frame,
                schema=schema,
                shape=shape,
                config=config,
                roles=roles,
                additive=additive,
                deadline=deadline,
                rolled_up=rolled_up() if request.task in _ROW_LEVEL else None,
            )
        except Exception:
            logger.exception("measured_analysis_failed", task=request.task)
            return not_run(request.task, _FAILED, request.target)

    if requests is not None:
        items = [attempt(r) for r in requests]
    else:
        items = _default_plan(work, schema, shape, config, roles, measure_roles, attempt)

    seen: set[tuple[str, str]] = set()
    excluded: list[Exclusion] = []
    for item in items:
        for exclusion in item.leakage:
            key = (exclusion.column, exclusion.reason)
            if key not in seen:
                seen.add(key)
                excluded.append(exclusion)
    return MeasuredAnalysis(
        version=MEASURED_VERSION,
        seed=config.seed,
        n_rows=len(frame),
        sampled_rows=sampled,
        items=items,
        excluded=excluded,
        seconds=round(time.monotonic() - started, 2),
    )


def _default_plan(
    work: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    config: MeasuredConfig,
    roles: dict[str, str],
    measure_roles: Collection[str],
    attempt: Callable[[MeasuredRequest], MeasuredItem],
) -> list[MeasuredItem]:
    items: list[MeasuredItem] = []
    target = pick_target(work, schema, shape, config, roles, measure_roles)
    regression: MeasuredItem | None = None
    if target is not None:
        regression = attempt(MeasuredRequest(task="driver_regression", target=target))
        items.append(regression)
    class_target = pick_class_target(work, schema, shape, config, roles, avoid=target)
    if class_target is not None:
        items.append(attempt(MeasuredRequest(task="driver_classification", target=class_target)))
    if len(numeric_columns(work, schema, shape, config, roles=roles)) >= 2:
        items.append(attempt(MeasuredRequest(task="segments")))
        items.append(attempt(MeasuredRequest(task="anomalies")))
    if shape.time_column is not None:
        forecast_target = target or pick_forecast_target(
            work, schema, shape, config, roles, measure_roles
        )
        if forecast_target is not None:
            items.append(attempt(MeasuredRequest(task="forecast", target=forecast_target)))
    if regression is not None and regression.status == "ok":
        top = regression.values.get("top_feature")
        if (
            isinstance(top, str)
            and schema.role_of(top) in {ColumnRole.NUMERIC, ColumnRole.ORDINAL}
            and top in regression.features
        ):
            items.append(attempt(MeasuredRequest(task="threshold", target=target, features=[top])))
    return items


__all__ = ["compute_measured", "pick_class_target", "pick_target"]
