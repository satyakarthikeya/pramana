"""Planted tables for the Measured tier: every answer is set by the generator below.

Sizes are small and every generator is seeded, so each known answer is reproducible and
each test is fast. The planted structure is described in each docstring.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pramana.analysis import infer_schema, load_config
from pramana.analysis.measured import MeasuredConfig, load_measured_config
from pramana.analysis.schema_inference import SchemaProfile
from pramana.analysis.shape import ShapeProfile, classify_shape


def fast_config(**overrides: object) -> MeasuredConfig:
    """The shipped config with fewer folds, trees and repeats so a test takes seconds."""
    base = load_measured_config()
    grids = base.grids.model_copy(
        update={
            "ridge_alpha": [1.0, 10.0],
            "forest_trees": 15,
            "forest_depth": [4],
            "boosting_trees": 15,
            "boosting_depth": [2],
            "svm_c": [1.0],
            "logistic_c": [1.0],
        }
    )
    segments = base.segments.model_copy(update={"null_repeats": 3, "bootstrap_repeats": 8})
    threshold = base.threshold.model_copy(update={"bootstrap_repeats": 10})
    importance = base.importance.model_copy(update={"repeats": 2})
    update = {
        "outer_folds": 3,
        "inner_folds": 2,
        "min_rows": 40,
        "min_class_rows": 10,
        "grids": grids,
        "segments": segments,
        "threshold": threshold,
        "importance": importance,
        **overrides,
    }
    return base.model_copy(update=update)


def prepare(
    frame: pd.DataFrame, min_non_null: int | None = None
) -> tuple[SchemaProfile, ShapeProfile]:
    """Schema and shape; `min_non_null` lowers the schema's row floor for short tables."""
    inference = load_config().schema_inference
    if min_non_null is not None:
        inference = inference.model_copy(update={"min_non_null": min_non_null})
    schema = infer_schema(frame, inference)
    return schema, classify_shape(frame, schema)


def driver_table(n: int = 300, seed: int = 1) -> pd.DataFrame:
    """`sales` = 3 * ad_spend + noise (sd 1); `footfall` and `region` are unrelated;
    `noise_target` is pure noise; `row_id` counts rows; `is_high` is the top third of sales
    with a flip rate of 3%."""
    rng = np.random.default_rng(seed)
    ad = rng.normal(size=n)
    frame = pd.DataFrame(
        {
            "ad_spend": ad,
            "footfall": rng.normal(size=n),
            "temperature": rng.normal(size=n),
            "region": rng.choice(["north", "south", "east"], n),
        }
    )
    frame["sales"] = 3 * ad + rng.normal(size=n)
    frame["noise_target"] = rng.normal(size=n)
    frame["row_id"] = np.arange(n)
    high = frame["sales"] > frame["sales"].quantile(2 / 3)
    flip = rng.random(n) < 0.03
    frame["is_high"] = np.where(high ^ flip, "high", "normal")
    return frame


def leaky_table(n: int = 300, seed: int = 2) -> pd.DataFrame:
    """revenue depends on `ad_spend`; `net` = revenue - cost exactly; `rev_copy` is revenue
    with 1% noise; `row_id` is unique per row."""
    rng = np.random.default_rng(seed)
    ad = rng.normal(size=n)
    revenue = 100 + 10 * ad + rng.normal(scale=5, size=n)
    cost = 40 + rng.normal(scale=3, size=n)
    return pd.DataFrame(
        {
            "revenue": revenue,
            "ad_spend": ad,
            "cost": cost,
            "net": revenue - cost,
            "rev_copy": revenue * (1 + rng.normal(scale=0.01, size=n)),
            "row_id": np.arange(n),
        }
    )


def three_blobs(n: int = 300, seed: int = 3) -> pd.DataFrame:
    """Three well-separated groups of 100 rows in three columns."""
    rng = np.random.default_rng(seed)
    centres = np.array([[0.0, 0.0, 0.0], [8.0, 8.0, 0.0], [0.0, 8.0, 8.0]])
    parts = [centres[i] + rng.normal(scale=1.0, size=(n // 3, 3)) for i in range(3)]
    return pd.DataFrame(np.vstack(parts), columns=["a", "b", "c"])


def no_clusters(n: int = 300, seed: int = 4) -> pd.DataFrame:
    """One Gaussian cloud, columns independent: there is no grouping to find."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.normal(size=(n, 3)), columns=["a", "b", "c"])


PLANTED_OUTLIER_ROWS = (10, 80, 150, 220)


def outlier_table(n: int = 300, seed: int = 5) -> pd.DataFrame:
    """`x2` follows `x1` closely, so a row with x1 = 2 and x2 = -2 breaks the pattern while
    each of its values is ordinary on its own. Four such rows are planted (0-based)."""
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    x2 = x1 + rng.normal(scale=0.15, size=n)
    x3 = rng.normal(size=n)
    for i, position in enumerate(PLANTED_OUTLIER_ROWS):
        x1[position] = 2.0 if i % 2 == 0 else -2.0
        x2[position] = -x1[position]
    return pd.DataFrame({"x1": x1, "x2": x2, "x3": x3})


def monthly_series(months: int = 48, seed: int = 6) -> pd.DataFrame:
    """revenue = 100 + 2 * t + 15 * sin(2 pi t / 12) + noise (sd 2); one row per month."""
    rng = np.random.default_rng(seed)
    t = np.arange(months)
    revenue = 100 + 2 * t + 15 * np.sin(2 * np.pi * t / 12) + rng.normal(scale=2, size=months)
    dates = pd.date_range("2021-01-01", periods=months, freq="MS").strftime("%Y-%m-%d")
    return pd.DataFrame({"month": dates, "revenue": revenue})


PLANTED_BEND = 5.0


def bend_table(n: int = 300, seed: int = 7) -> pd.DataFrame:
    """y is flat for x below 5 and rises 2 per unit above it, plus noise (sd 0.5)."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(0, 10, n)
    y = 2 * np.maximum(0, x - PLANTED_BEND) + rng.normal(scale=0.5, size=n)
    return pd.DataFrame({"x": x, "y": y})
