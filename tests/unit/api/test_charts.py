"""Chart data is descriptive only: deterministic, bounded and drawn from the real table."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pramana.api.charts import (
    MAX_SCATTER_POINTS,
    claim_chart,
    data_overview,
)
from pramana.api.models import GroupsChart, ScatterChart
from pramana.contracts import CandidateInsight, ClaimType


def _candidate(claim_type: ClaimType, variables: list[str]) -> CandidateInsight:
    return CandidateInsight(
        insight_id="c1",
        claim="a is associated with b",
        claim_type=claim_type,
        variables=variables,
        dataset_ref="ref",
        analysis_evidence={"stat": "x", "raw_value": 0.1, "n_observations": 10},
    )


def _frame(rows: int = 2000) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    a = rng.normal(size=rows)
    return pd.DataFrame(
        {
            "a": a,
            "b": a * 2 + rng.normal(size=rows),
            "sex": np.where(np.arange(rows) % 2 == 0, "f", "m"),
        }
    )


def test_scatter_is_bounded_deterministic_and_reports_full_n() -> None:
    frame = _frame()
    candidate = _candidate(ClaimType.CORRELATION, ["a", "b"])
    first = claim_chart(candidate, frame)
    second = claim_chart(candidate, frame)
    assert isinstance(first, ScatterChart)
    assert first == second
    assert first.n == 2000
    assert first.shown == MAX_SCATTER_POINTS
    assert len(first.points) == MAX_SCATTER_POINTS
    assert len(first.fit) == 2


def test_scatter_drops_incomplete_rows_and_never_emits_non_finite_values() -> None:
    frame = _frame(50)
    frame.loc[0, "a"] = np.nan
    frame.loc[1, "b"] = np.inf
    chart = claim_chart(_candidate(ClaimType.TREND, ["a", "b"]), frame)
    assert isinstance(chart, ScatterChart)
    assert chart.n == 48
    assert all(np.isfinite(x) and np.isfinite(y) for x, y in chart.points)


def test_group_chart_summarises_each_group_from_the_data() -> None:
    frame = _frame(400)
    chart = claim_chart(_candidate(ClaimType.GROUP_DIFFERENCE, ["sex", "b"]), frame)
    assert isinstance(chart, GroupsChart)
    assert [g.label for g in chart.groups] == ["f", "m"]
    female = frame.loc[frame["sex"] == "f", "b"]
    assert chart.groups[0].n == len(female)
    assert chart.groups[0].median == float(np.percentile(female, 50))
    assert chart.groups[0].minimum <= chart.groups[0].q1 <= chart.groups[0].median
    assert chart.groups[0].median <= chart.groups[0].q3 <= chart.groups[0].maximum


def test_unknown_columns_or_untestable_types_give_no_chart() -> None:
    frame = _frame(20)
    assert claim_chart(_candidate(ClaimType.CORRELATION, ["a", "missing"]), frame) is None
    assert claim_chart(_candidate(ClaimType.DISTRIBUTION, ["a", "b"]), frame) is None


def test_overview_describes_numeric_and_category_columns() -> None:
    frame = _frame(300)
    overview = data_overview(frame, ["a", "b", "sex", "not_a_column"])
    assert overview.rows == 300
    assert [c.name for c in overview.columns] == ["a", "b", "sex"]
    numeric = overview.columns[0]
    assert numeric.kind == "numeric"
    assert sum(b.count for b in numeric.bins) == 300
    assert overview.columns[2].kind == "category"
    assert {item.label for item in overview.columns[2].top} == {"f", "m"}
    assert overview.correlations is not None
    assert overview.correlations.columns == ["a", "b"]
    assert overview.correlations.values[0][0] == 1.0
