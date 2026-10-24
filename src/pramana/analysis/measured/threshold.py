"""M7: does one bend in the pattern beat a straight line on rows it did not see?

Guarantees: the bend's position is searched on training rows only (a grid of quantiles of
the column that leaves a configured share of rows on each side); the comparison is the
held-out R² of the one-bend line minus that of a plain straight line on the same folds;
the bend's position is reported with a bootstrap range. Without a lift over the straight
line the result is "no threshold", which is shown.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pramana.analysis.computed.charts import LineChart
from pramana.analysis.measured.common import TITLES, clean, not_run, row, sd, withheld_item
from pramana.analysis.measured.common import label as _label
from pramana.analysis.measured.config import MeasuredConfig
from pramana.analysis.measured.leakage import lint_features
from pramana.analysis.measured.models import MeasuredItem
from pramana.analysis.measured.prep import (
    build_table,
    eligible_columns,
    folds,
    held_out_blocker,
    num,
    outer_splitter,
)
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile
from pramana.analysis.shape import ShapeProfile


def _design(x: np.ndarray, bend: float) -> np.ndarray:
    return np.column_stack([np.ones(len(x)), x, np.maximum(0.0, x - bend)])


def fit_bend(x: np.ndarray, y: np.ndarray, config: MeasuredConfig) -> tuple[float, np.ndarray]:
    """The grid position with the smallest squared error, and the coefficients there."""
    cfg = config.threshold
    grid = np.unique(
        np.quantile(x, np.linspace(cfg.edge_fraction, 1 - cfg.edge_fraction, cfg.grid_points))
    )
    best: tuple[float, float, np.ndarray] | None = None
    for bend in grid:
        design = _design(x, float(bend))
        coef, *_ = np.linalg.lstsq(design, y, rcond=None)
        sse = float(np.sum((y - design @ coef) ** 2))
        if best is None or sse < best[0]:
            best = (sse, float(bend), coef)
    assert best is not None
    return best[1], best[2]


def _r2(y: np.ndarray, predicted: np.ndarray) -> float:
    total = float(np.sum((y - y.mean()) ** 2))
    return 1 - float(np.sum((y - predicted) ** 2)) / total if total > 0 else 0.0


def run_threshold(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    *,
    target: str,
    variable: str,
    config: MeasuredConfig,
    roles: dict[str, str] | None = None,
) -> MeasuredItem:
    """M7 for a numeric `variable` against a numeric `target`."""
    kind = "threshold"
    if blocker := held_out_blocker(shape):
        return not_run(kind, blocker, target)
    for name in (target, variable):
        if name not in frame.columns:
            return not_run(kind, f"{name} is not a column of the table.", target)
        if schema.role_of(name) not in {ColumnRole.NUMERIC, ColumnRole.ORDINAL}:
            return not_run(kind, f"{name} must be a numeric column.", target)
    if variable == target:
        return not_run(kind, "The column and the target must be different.", target)
    y = num(frame[target])
    pool, out = eligible_columns(frame, schema, [variable], config=config)
    kept, flagged = lint_features(
        frame,
        schema,
        target,
        y,
        pool,
        task="regression",
        config=config,
        roles=roles,
        proxy_check=False,
    )
    out = [*out, *flagged]
    if variable not in kept:
        item = not_run(kind, f"{variable} could not be used (see the excluded columns).", target)
        return item.model_copy(update={"leakage": out})
    table = build_table(frame, schema, shape, [variable], y)
    table_x = table.X[variable]
    usable = table_x.notna()
    if int(usable.sum()) < config.min_rows:
        item = not_run(kind, f"Fewer than {config.min_rows} usable rows.", target)
        return item.model_copy(update={"leakage": out})
    planned = outer_splitter(table, config, classification=False)
    if planned is None:
        item = not_run(kind, "Too few periods or entities to hold data out in order.", target)
        return item.model_copy(update={"leakage": out})
    cv, split_text = planned
    x_all, y_all = table_x.to_numpy(dtype=float), table.y.to_numpy(dtype=float)

    straight, bent = [], []
    for train, test in folds(table, cv):
        tr = train[usable.to_numpy()[train]]
        te = test[usable.to_numpy()[test]]
        if len(tr) < 10 or len(te) < 3:
            continue
        bend, coef = fit_bend(x_all[tr], y_all[tr], config)
        line, *_ = np.linalg.lstsq(_design(x_all[tr], np.inf), y_all[tr], rcond=None)
        straight.append(_r2(y_all[te], _design(x_all[te], np.inf) @ line))
        bent.append(_r2(y_all[te], _design(x_all[te], bend) @ coef))
    if len(bent) < 2:
        item = not_run(kind, "Too few held-out folds could be scored.", target)
        return item.model_copy(update={"leakage": out})
    lifts = [b - s for b, s in zip(bent, straight, strict=True)]
    lift, spread = float(np.mean(lifts)), sd(lifts)

    mask = usable.to_numpy()
    x_u, y_u = x_all[mask], y_all[mask]
    bend, coef = fit_bend(x_u, y_u, config)
    rng = np.random.default_rng(config.seed)
    bends = []
    for _ in range(config.threshold.bootstrap_repeats):
        pick = rng.integers(0, len(x_u), len(x_u))
        bends.append(fit_bend(x_u[pick], y_u[pick], config)[0])
    low, high = (float(v) for v in np.quantile(bends, [0.05, 0.95]))
    low, high = min(low, bend), max(high, bend)  # the range always contains the estimate
    slope_below, slope_above = float(coef[1]), float(coef[1] + coef[2])

    values = {
        "bend_at": bend,
        "bend_range_low": low,
        "bend_range_high": high,
        "slope_below": slope_below,
        "slope_above": slope_above,
        "r2_straight": float(np.mean(straight)),
        "r2_one_bend": float(np.mean(bent)),
        "folds_scored": len(bent),
        "bootstrap_repeats": config.threshold.bootstrap_repeats,
    }
    common = dict(
        id=f"{kind}:{variable}~{target}",
        kind=kind,
        title=f"{TITLES[kind]}: {_label(variable)} and {_label(target)}",
        target=target,
        features=[variable],
        model_family="one-bend line",
        models_tried=config.threshold.grid_points,
        split=split_text,
        baseline="straight line",
        metric="R²",
        baseline_score=float(np.mean(straight)),
        model_score=float(np.mean(bent)),
        lift=lift,
        spread=spread,
        n_rows=int(mask.sum()),
        leakage=out,
        values={k: clean(v) for k, v in values.items()},
    )
    common["values"] = {**common["values"], "lift_floor": config.lift_floor}  # type: ignore[dict-item]
    if float(np.mean(bent)) >= config.too_good_cutoff:
        return withheld_item(
            common,
            score=float(np.mean(bent)),
            metric="R²",
            cutoff=config.too_good_cutoff,
            subject=_label(target),
        )
    if lift <= config.lift_floor:
        return MeasuredItem(
            status="no_lift",
            sentence=(
                f"No threshold: a line with one bend did not beat a straight line on held-out "
                f"rows (lift {lift:.2f} in R² against a floor of {config.lift_floor:.2f})."
            ),
            **common,
        )
    xs = np.linspace(float(x_u.min()), float(x_u.max()), config.threshold.max_chart_points)
    fitted = _design(xs, bend) @ coef
    nearest = int(np.argmin(np.abs(xs - bend)))
    points = [(f"{x:.3g}", float(v)) for x, v in zip(xs, fitted, strict=True)]
    return MeasuredItem(
        status="ok",
        sentence=(
            f"A line with one bend beats a straight line by {lift:.2f} in R² on rows it did not "
            f"see (± {spread:.2f} between folds, {split_text}). The bend is at "
            f"{_label(variable)} = {bend:.3g} (bootstrap range {low:.3g} to {high:.3g}); the "
            f"slope is {slope_below:.2f} below it and {slope_above:.2f} above it."
        ),
        table=[
            row(part="below the bend", slope=slope_below),
            row(part="above the bend", slope=slope_above),
        ],
        chart=LineChart(
            x_label=_label(variable),
            y_label=_label(target),
            points=points,
            marks=[points[nearest][0]],
        ),
        **common,
    )
