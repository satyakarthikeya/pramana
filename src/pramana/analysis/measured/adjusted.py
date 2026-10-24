"""M3: how much held-out skill a column adds once listed controls are already in the model.

Guarantees: both models are plain linear (ridge with a fixed small penalty, or logistic
regression) fitted on the same training rows of each fold; the lift is the held-out score
WITH the variable minus the score WITHOUT it; the partial effect is a standardised
coefficient from the training rows, and `sign agreement` is the share of folds whose
coefficient has the sign of the average. No choice is tuned, so there is no inner search.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import r2_score, roc_auc_score
from sklearn.pipeline import Pipeline

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
    preprocessor,
)
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile
from pramana.analysis.shape import ShapeProfile

_RIDGE_ALPHA = 1.0


def run_adjusted(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    *,
    target: str,
    variable: str,
    controls: list[str],
    config: MeasuredConfig,
    roles: dict[str, str] | None = None,
) -> MeasuredItem:
    """Held-out lift from adding `variable` to a linear model that already has `controls`."""
    kind = "adjusted_association"
    if blocker := held_out_blocker(shape):
        return not_run(kind, blocker, target)
    item_id = f"{kind}:{variable}~{target}"
    for name in (target, variable, *controls):
        if name not in frame.columns:
            return not_run(kind, f"{name} is not a column of the table.", target)
    if variable == target or target in controls or variable in controls:
        return not_run(kind, "The target, the variable and the controls must be different.", target)
    if schema.role_of(variable) not in {ColumnRole.NUMERIC, ColumnRole.ORDINAL}:
        return not_run(kind, f"{variable} must be a numeric column.", target)
    binary = False
    if schema.role_of(target) in {ColumnRole.NUMERIC, ColumnRole.ORDINAL}:
        y = num(frame[target])
        metric, baseline_name = "R²", "model without the variable"
    else:
        labels = frame[target].dropna().astype(str)
        if labels.nunique() != 2:
            return not_run(kind, f"{target} must be numeric or have exactly two groups.", target)
        first = sorted(labels.unique())[0]
        y = frame[target].map(lambda v: np.nan if pd.isna(v) else float(str(v) != first))
        binary = True
        metric, baseline_name = "AUC", "model without the variable"
    pool, out = eligible_columns(frame, schema, [variable, *controls], config=config)
    task = "classification" if binary else "regression"
    y_for_lint = y.map(lambda v: v if pd.isna(v) else str(int(v))) if binary else y
    kept, flagged = lint_features(
        frame, schema, target, y_for_lint, pool, task=task, config=config, roles=roles
    )
    out = [*out, *flagged]
    if variable not in kept:
        item = not_run(kind, f"{variable} could not be used (see the excluded columns).", target)
        return item.model_copy(update={"leakage": out})
    controls_kept = [c for c in controls if c in kept]
    if not controls_kept:
        item = not_run(kind, "The controls could not be used (see the excluded columns).", target)
        return item.model_copy(update={"leakage": out})

    columns = [variable, *controls_kept]
    table = build_table(frame, schema, shape, columns, y)
    if len(table.y) < config.min_rows:
        item = not_run(kind, f"Fewer than {config.min_rows} usable rows.", target)
        return item.model_copy(update={"leakage": out})
    planned = outer_splitter(table, config, classification=binary)
    if planned is None:
        item = not_run(kind, "Too few periods or entities to hold data out in order.", target)
        return item.model_copy(update={"leakage": out})
    cv, split_text = planned

    def model() -> object:
        return LogisticRegression(max_iter=1000, C=1.0) if binary else Ridge(alpha=_RIDGE_ALPHA)

    with_scores: list[float] = []
    without_scores: list[float] = []
    coefficients: list[float] = []
    for train, test in folds(table, cv):
        ytr, yte = table.y.iloc[train], table.y.iloc[test]
        if binary and (ytr.nunique() < 2 or yte.nunique() < 2):
            continue
        fits = {}
        for name, cols in (("with", columns), ("without", controls_kept)):
            pipe = Pipeline([("prep", preprocessor(table.X[cols])), ("model", model())])
            pipe.fit(table.X[cols].iloc[train], ytr)
            fits[name] = pipe
        scores = {}
        for name, cols in (("with", columns), ("without", controls_kept)):
            Xte = table.X[cols].iloc[test]
            scores[name] = (
                roc_auc_score(yte, fits[name].predict_proba(Xte)[:, 1])
                if binary
                else r2_score(yte, fits[name].predict(Xte))
            )
        with_scores.append(float(scores["with"]))
        without_scores.append(float(scores["without"]))
        # the variable's own column comes first among the numeric inputs, so its
        # standardised coefficient is the first one
        fitted = fits["with"].named_steps["model"]
        coef = fitted.coef_.ravel()[0]
        coefficients.append(float(coef))
    if len(with_scores) < 2:
        item = not_run(kind, "Too few held-out folds could be scored.", target)
        return item.model_copy(update={"leakage": out})

    lifts = [a - b for a, b in zip(with_scores, without_scores, strict=True)]
    lift, spread = float(np.mean(lifts)), sd(lifts)
    mean_coef = float(np.mean(coefficients))
    agree = float(np.mean([np.sign(c) == np.sign(mean_coef) for c in coefficients]))
    values = {
        "model_with": float(np.mean(with_scores)),
        "model_without": float(np.mean(without_scores)),
        "partial_effect_per_sd": mean_coef,
        "sign_agreement": agree,
        "folds_scored": len(lifts),
        "n_controls": len(controls_kept),
    }
    common = dict(
        id=item_id,
        kind=kind,
        title=f"{TITLES[kind]}: {_label(variable)} and {_label(target)}",
        target=target,
        features=columns,
        model_family="logistic regression" if binary else "ridge regression",
        models_tried=2,
        split=split_text,
        baseline=baseline_name,
        metric=metric,
        baseline_score=float(np.mean(without_scores)),
        model_score=float(np.mean(with_scores)),
        lift=lift,
        spread=spread,
        n_rows=len(table.y),
        leakage=out,
        values={k: clean(v) for k, v in values.items()},
    )
    common["values"] = {**common["values"], "lift_floor": config.lift_floor}  # type: ignore[dict-item]
    if float(np.mean(with_scores)) >= config.too_good_cutoff:
        return withheld_item(
            common,
            score=float(np.mean(with_scores)),
            metric=metric,
            cutoff=config.too_good_cutoff,
            subject=_label(target),
        )
    if metric == "R²" and float(np.mean(with_scores)) <= config.lift_floor:
        return MeasuredItem(
            status="no_lift",
            sentence=(
                f"The model with {_label(variable)} and the controls predicted held-out rows no "
                f"better than their own average (R² {float(np.mean(with_scores)):.2f}), so no "
                f"adjusted association is reported."
            ),
            **common,
        )
    if lift <= config.lift_floor:
        return MeasuredItem(
            status="no_lift",
            sentence=(
                f"Adding {_label(variable)} did not improve held-out {metric} beyond the "
                f"controls: the lift was {lift:.2f} against a floor of {config.lift_floor:.2f}."
            ),
            **common,
        )
    direction = "higher" if mean_coef > 0 else "lower"
    return MeasuredItem(
        status="ok",
        sentence=(
            f"With {len(controls_kept)} control columns held in the model, adding "
            f"{_label(variable)} raises the held-out {metric} for {_label(target)} by "
            f"{lift:.2f} (± {spread:.2f} between folds, {split_text}). Larger values of "
            f"{_label(variable)} go with {direction} {_label(target)}, and the sign of that "
            f"association matched in {agree * 100:.0f}% of folds."
        ),
        table=[
            row(
                column=variable,
                effect_per_sd=mean_coef,
                sign_agreement_pct=agree * 100,
                lift=lift,
            )
        ],
        **common,
    )
