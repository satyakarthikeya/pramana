"""Descriptive profiles and exploratory relationship evidence."""

from __future__ import annotations

from typing import Any

import pandas as pd
from scipy import stats


def _json_number(value: Any) -> float | None:
    return None if pd.isna(value) else float(value)


def profile_dataset(
    dataframe: pd.DataFrame,
    *,
    max_relationships: int = 1000,
) -> dict[str, Any]:
    """Profile a dataframe and return evidence, never verification verdicts."""

    numeric = dataframe.select_dtypes(include="number").columns.tolist()
    categorical = dataframe.select_dtypes(exclude="number").columns.tolist()
    numeric_profiles: dict[str, dict[str, Any]] = {}
    for column in numeric:
        series = dataframe[column]
        numeric_profiles[str(column)] = {
            "count": int(series.count()),
            "missing_count": int(series.isna().sum()),
            "mean": _json_number(series.mean()),
            "median": _json_number(series.median()),
            "std": _json_number(series.std()),
            "min": _json_number(series.min()),
            "max": _json_number(series.max()),
            "q25": _json_number(series.quantile(0.25)),
            "q75": _json_number(series.quantile(0.75)),
            "unique_count": int(series.nunique(dropna=True)),
            "variance": _json_number(series.var()),
            "skewness": _json_number(series.skew()),
        }

    categorical_profiles: dict[str, dict[str, Any]] = {}
    for column in categorical:
        series = dataframe[column]
        frequencies = series.fillna("<MISSING>").value_counts().head(20)
        categorical_profiles[str(column)] = {
            "unique_count": int(series.nunique(dropna=True)),
            "missing_count": int(series.isna().sum()),
            "most_frequent": None if frequencies.empty else str(frequencies.index[0]),
            "frequencies": {str(key): int(value) for key, value in frequencies.items()},
        }

    return {
        "dataset": {"rows": len(dataframe), "columns": len(dataframe.columns)},
        "numeric_features": [str(column) for column in numeric],
        "categorical_features": [str(column) for column in categorical],
        "binary_features": [
            str(column)
            for column in dataframe.columns
            if dataframe[column].nunique(dropna=True) == 2
        ],
        "ordinal_like_features": [
            str(column)
            for column in numeric
            if dataframe[column].nunique(dropna=True) <= 20
        ],
        "time_features": [
            str(column)
            for column in dataframe.columns
            if "time" in str(column).casefold()
            or str(column).casefold() in {"year", "date"}
        ],
        "identifier_features": [
            str(column)
            for column in dataframe.columns
            if any(
                token in str(column).casefold()
                for token in ("id", "identifier", "index", "key")
            )
            and dataframe[column].nunique(dropna=True) / max(len(dataframe), 1) >= 0.95
        ],
        "numeric_profiles": numeric_profiles,
        "categorical_profiles": categorical_profiles,
        "relationships": _discover_relationships(
            dataframe, numeric, categorical, max_relationships
        ),
    }


def _discover_relationships(
    dataframe: pd.DataFrame,
    numeric: list[str],
    categorical: list[str],
    max_relationships: int,
) -> list[dict[str, Any]]:
    """Calculate exploratory associations and group differences."""

    relationships: list[dict[str, Any]] = []
    for left_index, left in enumerate(numeric):
        for right in numeric[left_index + 1 :]:
            pair = dataframe[[left, right]].dropna()
            if len(pair) < 3 or pair[left].nunique() < 2 or pair[right].nunique() < 2:
                continue
            relationships.append(
                {
                    "relationship_type": "numeric_numeric_association",
                    "feature": str(left),
                    "target": str(right),
                    "analysis_methods": [
                        "pearson_correlation",
                        "spearman_correlation",
                    ],
                    "sample_size": len(pair),
                    "pearson": _json_number(pair[left].corr(pair[right])),
                    "spearman": _json_number(
                        pair[left].corr(pair[right], method="spearman")
                    ),
                    "test_executed": True,
                }
            )

    for category in categorical:
        for value in numeric:
            pair = dataframe[[category, value]].dropna()
            groups = [
                group[value].to_numpy()
                for _, group in pair.groupby(category, observed=True)
            ]
            groups = [group for group in groups if len(group) >= 2]
            if len(groups) < 2:
                continue
            method = "independent_t_test" if len(groups) == 2 else "anova"
            if any(pd.Series(group).nunique() < 2 for group in groups):
                relationships.append(
                    {
                        "relationship_type": "categorical_numeric_group_difference",
                        "feature": str(category),
                        "target": str(value),
                        "analysis_methods": [method],
                        "group_count": len(groups),
                        "sample_size": len(pair),
                        "test_executed": False,
                        "test_status": "skipped_constant_group",
                    }
                )
                continue
            if len(groups) == 2:
                statistic, p_value = stats.ttest_ind(*groups, equal_var=False)
            else:
                statistic, p_value = stats.f_oneway(*groups)
            relationships.append(
                {
                    "relationship_type": "categorical_numeric_group_difference",
                    "feature": str(category),
                    "target": str(value),
                    "analysis_methods": [method],
                    "group_count": len(groups),
                    "sample_size": len(pair),
                    "test_statistic": _json_number(statistic),
                    "p_value": _json_number(p_value),
                    "test_executed": True,
                }
            )

    for left_index, left in enumerate(categorical):
        for right in categorical[left_index + 1 :]:
            pair = dataframe[[left, right]].dropna()
            table = pd.crosstab(pair[left], pair[right])
            if table.shape[0] < 2 or table.shape[1] < 2:
                continue
            statistic, p_value, _, _ = stats.chi2_contingency(table)
            relationships.append(
                {
                    "relationship_type": "categorical_categorical_dependence",
                    "feature": str(left),
                    "target": str(right),
                    "analysis_methods": ["chi_square"],
                    "sample_size": len(pair),
                    "test_statistic": _json_number(statistic),
                    "p_value": _json_number(p_value),
                    "test_executed": True,
                }
            )
    return relationships[:max_relationships]
