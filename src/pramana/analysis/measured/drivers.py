"""M1 and M2: how well a closed menu of models predicts a column on rows it did not see.

Guarantees: every score is from held-out rows of an OUTER fold; the choice between the
grid settings and between the four model families is made inside each training part
(nested cross-validation), so the reported score is not the tuned score; preprocessing is
inside the pipeline, fitted on training rows only; the baseline is scored on the same
folds; permutation importance is measured on held-out rows with correlated columns
shuffled together. A result with no lift over the baseline is returned as `no_lift`, which
is an answer, not an error.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, clone
from sklearn.compose import TransformedTargetRegressor
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import balanced_accuracy_score, r2_score
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC, SVR

from pramana.analysis.computed.charts import Bar, BarChart
from pramana.analysis.measured.common import (
    TITLES,
    clean,
    not_run,
    row,
    sd,
    withheld_item,
)
from pramana.analysis.measured.common import label as _label
from pramana.analysis.measured.config import MeasuredConfig
from pramana.analysis.measured.leakage import lint_features
from pramana.analysis.measured.models import MeasuredItem
from pramana.analysis.measured.prep import (
    Table,
    build_table,
    eligible_columns,
    folds,
    held_out_blocker,
    inner_splitter,
    num,
    outer_splitter,
    preprocessor,
)
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile
from pramana.analysis.shape import ShapeProfile
from pramana.common.logging import get_logger

logger = get_logger(component="measured")

Task = Literal["regression", "classification"]


@dataclass(frozen=True)
class Family:
    key: str
    label: str
    estimator: BaseEstimator
    grid: dict[str, list[Any]]

    @property
    def size(self) -> int:
        total = 1
        for values in self.grid.values():
            total *= len(values)
        return total


def families(task: Task, config: MeasuredConfig, n_rows: int | None = None) -> list[Family]:
    """The closed menu, with its fixed grids from config. Nothing else can be fitted.

    Support vector machines are left out of a table with more than `svm_max_rows` rows.
    """
    menu = _menu(task, config)
    if n_rows is not None and n_rows > config.grids.svm_max_rows:
        menu = [f for f in menu if f.key != "svm"]
    return menu


def _menu(task: Task, config: MeasuredConfig) -> list[Family]:
    g, seed = config.grids, config.seed
    if task == "regression":
        return [
            Family("ridge", "ridge regression", Ridge(), {"model__alpha": g.ridge_alpha}),
            Family(
                "forest",
                "random forest",
                RandomForestRegressor(n_estimators=g.forest_trees, random_state=seed, n_jobs=1),
                {"model__max_depth": g.forest_depth},
            ),
            Family(
                "boosting",
                "gradient boosting",
                GradientBoostingRegressor(n_estimators=g.boosting_trees, random_state=seed),
                {
                    "model__max_depth": g.boosting_depth,
                    "model__learning_rate": g.boosting_rate,
                },
            ),
            Family(
                "svm",
                "support vector machine",
                TransformedTargetRegressor(regressor=SVR(), transformer=StandardScaler()),
                {"model__regressor__C": g.svm_c},
            ),
        ]
    return [
        Family(
            "logistic",
            "logistic regression",
            LogisticRegression(max_iter=1000, class_weight="balanced"),
            {"model__C": g.logistic_c},
        ),
        Family(
            "forest",
            "random forest",
            RandomForestClassifier(
                n_estimators=g.forest_trees,
                class_weight="balanced",
                random_state=seed,
                n_jobs=1,
            ),
            {"model__max_depth": g.forest_depth},
        ),
        Family(
            "boosting",
            "gradient boosting",
            GradientBoostingClassifier(n_estimators=g.boosting_trees, random_state=seed),
            {"model__max_depth": g.boosting_depth, "model__learning_rate": g.boosting_rate},
        ),
        Family(
            "svm",
            "support vector machine",
            SVC(class_weight="balanced", random_state=seed),
            {"model__C": g.svm_c},
        ),
    ]


def _score(task: Task, truth: pd.Series, predicted: np.ndarray) -> float:
    if task == "regression":
        return float(r2_score(truth, predicted))
    return float(balanced_accuracy_score(truth, predicted))


def feature_groups(X: pd.DataFrame, rho: float) -> list[list[str]]:
    """Columns that move together (|spearman| above `rho`) form one group; others stand alone."""
    parent = {c: c for c in X.columns}

    def find(c: str) -> str:
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c

    numeric = [c for c in X.columns if pd.api.types.is_numeric_dtype(X[c])]
    if len(numeric) > 1:
        corr = X[numeric].corr(method="spearman").abs()
        for i, a in enumerate(numeric):
            for b in numeric[i + 1 :]:
                if corr.loc[a, b] > rho:
                    parent[find(a)] = find(b)
    grouped: dict[str, list[str]] = {}
    for c in X.columns:
        grouped.setdefault(find(c), []).append(c)
    return list(grouped.values())


def grouped_importance(
    estimator: Any,
    X: pd.DataFrame,
    y: pd.Series,
    groups: list[list[str]],
    *,
    task: Task,
    repeats: int,
    rng: np.random.Generator,
) -> list[float]:
    """Mean drop in the held-out score when a group's columns are shuffled together."""
    base = _score(task, y, estimator.predict(X))
    drops: list[float] = []
    for columns in groups:
        scores = []
        for _ in range(repeats):
            shuffled = X.copy()
            order = rng.permutation(len(X))
            for column in columns:
                shuffled[column] = X[column].to_numpy()[order]
            scores.append(_score(task, y, estimator.predict(shuffled)))
        drops.append(base - float(np.mean(scores)))
    return drops


def _rank_agreement(vectors: list[list[float]]) -> float | None:
    """Mean pairwise Spearman correlation of the importance ranking between folds."""
    if len(vectors) < 2 or len(vectors[0]) < 2:
        return None
    values = []
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            a, b = pd.Series(vectors[i]), pd.Series(vectors[j])
            if a.nunique() > 1 and b.nunique() > 1:
                values.append(float(a.corr(b, method="spearman")))
    return float(np.mean(values)) if values else None


@dataclass
class FoldResult:
    model: float
    baseline: float
    family: str
    families: dict[str, float]
    importance: list[float]


def cross_validate(
    table: Table,
    task: Task,
    config: MeasuredConfig,
    cv: object,
    groups: list[list[str]],
    deadline: float | None = None,
) -> list[FoldResult]:
    """Nested cross-validation over the closed menu. Folds that cannot be scored are skipped,
    and no new fold starts after `deadline` (a `time.monotonic()` value) once two are done."""
    scoring = "r2" if task == "regression" else "balanced_accuracy"
    menu = families(task, config, len(table.y))
    rng = np.random.default_rng(config.seed)
    results: list[FoldResult] = []
    for train, test in folds(table, cv):
        if deadline is not None and len(results) >= 2 and time.monotonic() > deadline:
            break
        Xtr, Xte = table.X.iloc[train], table.X.iloc[test]
        ytr, yte = table.y.iloc[train], table.y.iloc[test]
        gtr = table.groups[train] if table.groups is not None else None
        n_groups = len(set(gtr)) if gtr is not None else None
        inner = inner_splitter(table.kind, n_groups, config)
        best: tuple[float, Family, GridSearchCV] | None = None
        per_family: dict[str, float] = {}
        for family in menu:
            pipe = Pipeline([("prep", preprocessor(Xtr)), ("model", clone(family.estimator))])
            search = GridSearchCV(pipe, family.grid, cv=inner, scoring=scoring, n_jobs=1)
            try:
                search.fit(Xtr, ytr, **({"groups": gtr} if gtr is not None else {}))
            except Exception:
                logger.warning("measured_fit_failed", family=family.key)
                continue
            per_family[family.key] = _score(task, yte, search.predict(Xte))
            if best is None or search.best_score_ > best[0]:
                best = (float(search.best_score_), family, search)
        if best is None:
            continue
        baseline = (
            DummyRegressor(strategy="mean")
            if task == "regression"
            else DummyClassifier(strategy="most_frequent")
        )
        baseline.fit(Xtr, ytr)
        _, family, search = best
        results.append(
            FoldResult(
                model=per_family[family.key],
                baseline=_score(task, yte, baseline.predict(Xte)),
                family=family.key,
                families=per_family,
                importance=grouped_importance(
                    search,
                    Xte,
                    yte,
                    groups,
                    task=task,
                    repeats=config.importance.repeats,
                    rng=rng,
                ),
            )
        )
    return results


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _group_name(columns: list[str]) -> str:
    return ", ".join(_label(c) for c in columns)


def candidate_features(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    target: str,
    config: MeasuredConfig,
    *,
    requested: list[str] | None = None,
) -> list[str]:
    """Columns offered to a model before any checks: the request, or every column that is
    a measurement or a label, ordered by completeness (never by relation to the target)."""
    skip = {target, shape.time_column, shape.entity_column} - {None}
    if requested:
        return [c for c in requested if c != target]
    usable = [
        c
        for c, p in schema.columns.items()
        if c not in skip
        and c in frame.columns
        and p.role
        in {ColumnRole.NUMERIC, ColumnRole.ORDINAL, ColumnRole.CATEGORICAL, ColumnRole.ID_LIKE}
    ]
    missing = {c: float(frame[c].isna().mean()) for c in usable}
    return sorted(usable, key=lambda c: missing[c])  # stable: ties keep column order


def run_driver(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    *,
    task: Task,
    target: str,
    config: MeasuredConfig,
    features: list[str] | None = None,
    roles: dict[str, str] | None = None,
    deadline: float | None = None,
) -> MeasuredItem:
    """M1 (task="regression") or M2 (task="classification") for one target column."""
    kind = "driver_regression" if task == "regression" else "driver_classification"
    if blocker := held_out_blocker(shape):
        return not_run(kind, blocker, target)
    if target not in frame.columns:
        return not_run(kind, f"{target} is not a column of the table.", target)
    role = schema.role_of(target)
    if task == "regression":
        if role not in {ColumnRole.NUMERIC, ColumnRole.ORDINAL}:
            return not_run(kind, f"{target} is not a numeric column.", target)
        y = num(frame[target])
        baseline_name, metric = "mean of the training rows", "R²"
    else:
        y = frame[target].astype("object").where(frame[target].notna(), np.nan)
        y = y.map(lambda v: v if isinstance(v, float) and np.isnan(v) else str(v))
        counts = y.value_counts()
        if not 2 <= len(counts) <= config.max_class_levels:
            return not_run(
                kind,
                f"{target} does not have between 2 and {config.max_class_levels} groups.",
                target,
            )
        if int(counts.min()) < config.min_class_rows:
            return not_run(
                kind,
                f"The smallest group of {target} has fewer than {config.min_class_rows} rows.",
                target,
            )
        baseline_name, metric = "most frequent group", "balanced accuracy"
    if int(y.notna().sum()) < config.min_rows:
        return not_run(
            kind, f"Fewer than {config.min_rows} rows have a value for {target}.", target
        )

    requested = features
    pool = candidate_features(frame, schema, shape, target, config, requested=requested)
    eligible, out = eligible_columns(frame, schema, pool, config=config)
    capped = eligible[: config.max_features * 2] if requested is None else eligible
    usable, flagged = lint_features(
        frame, schema, target, y, capped, task=task, config=config, roles=roles
    )
    out = [*out, *flagged]
    if requested is None:
        usable = usable[: config.max_features]
    if not usable:
        item = not_run(kind, f"No usable columns were left to predict {target}.", target)
        return item.model_copy(update={"leakage": out})

    table = build_table(frame, schema, shape, usable, y)
    if len(table.y) < config.min_rows:
        item = not_run(kind, f"Fewer than {config.min_rows} usable rows.", target)
        return item.model_copy(update={"leakage": out})
    planned = outer_splitter(table, config, classification=task == "classification")
    if planned is None:
        item = not_run(kind, "Too few periods or entities to hold data out in order.", target)
        return item.model_copy(update={"leakage": out})
    cv, split_text = planned
    groups = feature_groups(table.X, config.importance.correlated_rho)
    results = cross_validate(table, task, config, cv, groups, deadline)
    if len(results) < 2:
        item = not_run(kind, "The models could not be scored on enough held-out folds.", target)
        return item.model_copy(update={"leakage": out})

    menu = families(task, config, len(table.y))
    tried = sum(f.size for f in menu)
    lifts = [r.model - r.baseline for r in results]
    model_score = float(np.mean([r.model for r in results]))
    base_score = float(np.mean([r.baseline for r in results]))
    lift, spread = float(np.mean(lifts)), sd(lifts)
    chosen = Counter(r.family for r in results).most_common(1)[0][0]
    family = next(f for f in menu if f.key == chosen)
    values: dict[str, Any] = {
        "folds_scored": len(results),
        "n_features": len(usable),
        "feature_groups": len(groups),
    }
    for f in menu:
        scores = [r.families[f.key] for r in results if f.key in r.families]
        values[f"held_out_{f.key}"] = float(np.mean(scores)) if scores else None
        values[f"selected_{f.key}"] = sum(1 for r in results if r.family == f.key)

    common: dict[str, Any] = dict(
        id=f"{kind}:{target}",
        kind=kind,
        title=f"{TITLES[kind]}: {_label(target)}",
        target=target,
        features=usable,
        model_family=family.label,
        models_tried=tried,
        split=split_text,
        baseline=baseline_name,
        metric=metric,
        baseline_score=base_score,
        model_score=model_score,
        lift=lift,
        spread=spread,
        n_rows=len(table.y),
        leakage=out,
    )
    if model_score >= config.too_good_cutoff:
        return withheld_item(
            {**common, "values": clean_values(values)},
            score=model_score,
            metric=metric,
            cutoff=config.too_good_cutoff,
            subject=_label(target),
        )
    values["lift_floor"] = config.lift_floor
    if lift <= config.lift_floor:
        return MeasuredItem(
            status="no_lift",
            sentence=(
                f"No model beat the baseline on held-out data: the best lift was "
                f"{_fmt(lift)} {metric} against a floor of {_fmt(config.lift_floor)}."
            ),
            values=clean_values(values),
            **common,
        )

    drops = np.mean([r.importance for r in results], axis=0)
    positive = np.clip(drops, 0, None)
    total = float(positive.sum())
    shares = positive / total * 100 if total > 0 else np.zeros_like(positive)
    order = np.argsort(-shares, kind="stable")
    agreement = _rank_agreement([r.importance for r in results])
    values["rank_agreement"] = agreement
    table_rows = [
        row(
            feature=_group_name(groups[i]),
            share_pct=float(shares[i]),
            score_drop=float(drops[i]),
        )
        for i in order[:10]
    ]
    sentence = (
        f"A {family.label} beats the {baseline_name} baseline by {_fmt(lift)} in {metric} "
        f"on rows it did not see ({_fmt(model_score)} against {_fmt(base_score)}, "
        f"± {_fmt(spread)} between folds, {split_text}). It uses {len(usable)} columns "
        f"to predict {_label(target)}."
    )
    if total > 0:
        top = int(order[0])
        sentence += (
            f" {_group_name(groups[top])} accounts for {shares[top]:.0f}% of the model's "
            "held-out skill in this data."
        )
        values["top_share_pct"] = float(shares[top])
        values["top_feature"] = groups[top][0]
    chart = BarChart(
        x_label="Column",
        y_label="Share of the model's held-out skill (%)",
        bars=[Bar(label=_group_name(groups[i]), value=float(shares[i])) for i in order[:8]],
    )
    return MeasuredItem(
        status="ok",
        sentence=sentence,
        values=clean_values(values),
        table=table_rows,
        chart=chart,
        **common,
    )


def clean_values(values: dict[str, Any]) -> dict[str, Any]:
    return {k: clean(v) for k, v in values.items()}
