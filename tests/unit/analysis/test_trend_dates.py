"""A time axis read from a CSV is text; a trend claim on it must still be renderable."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pramana.analysis import infer_schema, load_config
from pramana.analysis.hypotheses import llm_proposer
from pramana.analysis.hypotheses.trend import _as_ordered_numeric


def test_text_dates_keep_their_order() -> None:
    values = _as_ordered_numeric(pd.Series(["2024-01-01", "2024-03-01", "2024-02-01", None]))
    assert values.iloc[0] < values.iloc[2] < values.iloc[1]
    assert values.isna().sum() == 1


def test_a_trend_on_text_months_is_rendered() -> None:
    months = pd.date_range("2021-01-01", periods=48, freq="MS").strftime("%Y-%m-%d")
    frame = pd.DataFrame(
        {
            "month": months,
            "revenue": 100 + np.arange(48) + np.random.default_rng(1).normal(0, 3, 48),
        }
    )
    config = load_config()
    schema = infer_schema(frame, config.schema_inference)
    claim = llm_proposer.StructuredClaim.model_validate(
        {
            "claim_type": "trend",
            "variables": ["month", "revenue"],
            "direction": "positive",
            "reference_group": None,
        }
    )
    candidate = llm_proposer.render_candidate(
        claim, frame, schema, config.hypotheses, dataset_ref="x", allowed=set(frame.columns)
    )
    assert candidate is not None
    assert candidate.analysis_evidence["raw_value"] > 0.8
