"""The leakage lint (PLAN §5.2.1): runs before any model and removes columns that would
make the score meaningless.

Guarantees: every exclusion carries a plain reason built from numbers this function
computed; a column is only ever removed, never added or changed; the lint looks at the
whole sampled table (it is a filter, not a fitted model, and it can only lower what a
model sees). Checked, in order: identifiers, survey weights, exact straight-line
restatements and sums or differences of the target, and single-feature proxies scored on
held-out rows.
"""

from __future__ import annotations

import re
from itertools import combinations
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, r2_score
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from pramana.analysis.measured.config import MeasuredConfig
from pramana.analysis.measured.models import Exclusion
from pramana.analysis.measured.prep import feature_frame, num, preprocessor
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile

Task = Literal["regression", "classification"]

#: Names that say a column identifies a record.
_ID_NAME = re.compile(r"(^|_)(id|key|seqn|code|no|num|number|index)$|^id", re.IGNORECASE)


def _is_identifier(
    frame: pd.DataFrame, schema: SchemaProfile, name: str, config: MeasuredConfig
) -> bool:
    if schema.role_of(name) is ColumnRole.ID_LIKE:
        return True
    values = frame[name].dropna()
    if len(values) < 3:
        return False
    if pd.api.types.is_float_dtype(values) and not (values % 1 == 0).all():
        return False  # a continuous measurement is distinct per row without being an id
    if values.nunique() / len(values) < config.leakage.id_unique_ratio:
        return False
    if not pd.api.types.is_numeric_dtype(values):
        return True  # distinct text per row names a record
    # A whole-number column distinct per row is an id only if it is named like one or
    # runs like a counter; revenue in whole rupees is distinct per row and is a measure.
    if _ID_NAME.search(name):
        return True
    span = float(values.max() - values.min()) + 1.0
    return span <= 1.5 * values.nunique()


def _line_match(y: np.ndarray, f: np.ndarray, config: MeasuredConfig) -> bool:
    """Whether y = a*f + b holds on nearly all complete rows (a least-squares line)."""
    if len(y) < config.leakage.identity_min_rows or np.ptp(f) == 0 or np.ptp(y) == 0:
        return False
    a, b = np.polyfit(f, y, 1)
    scale = np.maximum(np.abs(y), np.abs(a * f)) + 1e-12
    close = np.abs(y - (a * f + b)) <= config.leakage.identity_rel_tolerance * scale
    return bool(close.mean() >= config.leakage.identity_min_match)


def _pair_identity(
    y: np.ndarray, f: np.ndarray, g: np.ndarray, config: MeasuredConfig
) -> str | None:
    """ "sum", "fg" (f - g = y) or "gf" (g - f = y) when it holds on nearly all rows."""
    scale = np.maximum(np.abs(y), np.abs(f) + np.abs(g)) + 1e-12
    for label, residual in (("sum", y - (f + g)), ("fg", y - (f - g)), ("gf", y - (g - f))):
        close = np.abs(residual) <= config.leakage.identity_rel_tolerance * scale
        if close.mean() >= config.leakage.identity_min_match:
            return label
    return None


def _proxy_score(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    name: str,
    y: pd.Series,
    task: Task,
    config: MeasuredConfig,
) -> float | None:
    """Held-out score of one column alone with a shallow tree; None if it cannot be run."""
    X = feature_frame(frame, schema, [name])
    ok = y.notna()
    X, target = X[ok], y[ok]
    if len(target) < config.min_rows:
        return None
    tree = (
        DecisionTreeRegressor(max_depth=6, random_state=config.seed)
        if task == "regression"
        else DecisionTreeClassifier(max_depth=6, class_weight="balanced", random_state=config.seed)
    )
    pipe = Pipeline([("prep", preprocessor(X)), ("model", tree)])
    scores = []
    cv = KFold(n_splits=config.leakage.proxy_folds, shuffle=True, random_state=config.seed)
    for train, test in cv.split(X):
        pipe.fit(X.iloc[train], target.iloc[train])
        predicted = pipe.predict(X.iloc[test])
        scores.append(
            r2_score(target.iloc[test], predicted)
            if task == "regression"
            else balanced_accuracy_score(target.iloc[test], predicted)
        )
    return float(np.mean(scores))


def lint_features(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    target: str,
    y: pd.Series,
    columns: list[str],
    *,
    task: Task,
    config: MeasuredConfig,
    roles: dict[str, str] | None = None,
    proxy_check: bool = True,
) -> tuple[list[str], list[Exclusion]]:
    """Split `columns` into those a model may use and the excluded ones with reasons.

    `y` is the target as the model sees it (numbers for regression, labels for
    classification). The accounting-identity checks apply to numeric targets only.
    """
    roles = roles or {}
    kept: list[str] = []
    out: list[Exclusion] = []
    for name in columns:
        if name == target:
            continue
        if _is_identifier(frame, schema, name, config):
            out.append(
                Exclusion(
                    column=name,
                    reason=f"{name} looks like a row identifier, so it was not used to "
                    f"predict {target}.",
                )
            )
        elif roles.get(name) == "survey_weight":
            out.append(
                Exclusion(
                    column=name,
                    reason=f"{name} is a survey weight, not a measurement, so it was not "
                    f"used to predict {target}.",
                )
            )
        else:
            kept.append(name)

    if task == "regression":
        kept = _drop_identities(frame, schema, target, y, kept, out, config)

    survivors: list[str] = []
    for name in kept:
        score = _proxy_score(frame, schema, name, y, task, config) if proxy_check else None
        if score is not None and score >= config.leakage.proxy_cutoff:
            metric = "R²" if task == "regression" else "balanced accuracy"
            out.append(
                Exclusion(
                    column=name,
                    reason=f"{name} alone predicts {target} with a held-out {metric} of "
                    f"{score:.2f}, which is close to restating it, so it was not used.",
                )
            )
        else:
            survivors.append(name)
    return survivors, out


def _drop_identities(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    target: str,
    y: pd.Series,
    kept: list[str],
    out: list[Exclusion],
    config: MeasuredConfig,
) -> list[str]:
    numeric = [c for c in kept if schema.role_of(c) in {ColumnRole.NUMERIC, ColumnRole.ORDINAL}][
        : config.leakage.max_identity_columns
    ]
    data = pd.DataFrame({c: num(frame[c]) for c in numeric})
    data[target] = y
    removed: dict[str, str] = {}
    for name in numeric:
        both = data[[name, target]].dropna()
        if _line_match(both[target].to_numpy(), both[name].to_numpy(), config):
            removed[name] = (
                f"{name} is an exact straight-line restatement of {target}, so it was not "
                f"used to predict {target}."
            )
    for f, g in combinations([c for c in numeric if c not in removed], 2):
        both = data[[f, g, target]].dropna()
        if len(both) < config.leakage.identity_min_rows:
            continue
        found = _pair_identity(
            both[target].to_numpy(), both[f].to_numpy(), both[g].to_numpy(), config
        )
        if found is None:
            continue
        what = {
            "sum": f"{f} and {g} add up to {target}",
            "fg": f"{f} minus {g} equals {target}",
            "gf": f"{g} minus {f} equals {target}",
        }[found]
        for column in (f, g):
            removed.setdefault(column, f"{what} exactly, so neither was used to predict {target}.")
    for column, reason in removed.items():
        out.append(Exclusion(column=column, reason=reason))
    return [c for c in kept if c not in removed]
