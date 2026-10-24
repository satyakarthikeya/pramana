"""Segment profiles, nearest neighbours and components in the Measured tier.

Each expectation comes from the planted table, not from the code under test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.analysis.measured.components import run_components
from pramana.analysis.measured.drivers import families
from pramana.analysis.measured.segments import run_segments
from tests.unit.analysis import measured_fixtures as fx

CONFIG = fx.fast_config()


def _factors(n: int = 300, seed: int = 11) -> pd.DataFrame:
    """Two hidden factors: a1..a3 follow the first, b1..b3 follow the second."""
    rng = np.random.default_rng(seed)
    f1, f2 = rng.normal(size=n), rng.normal(size=n)
    cols = {f"a{i}": f1 + 0.4 * rng.normal(size=n) for i in (1, 2, 3)}
    cols.update({f"b{i}": f2 + 0.4 * rng.normal(size=n) for i in (1, 2, 3)})
    return pd.DataFrame(cols)


def test_components_find_the_two_planted_factors() -> None:
    frame = _factors()
    schema, shape = fx.prepare(frame)
    item = run_components(frame, schema, shape, config=CONFIG)
    assert item.status == "ok", item.sentence
    assert item.values["components_kept"] == 2
    # the first component loads on one block of columns only
    first = str(item.table[0]["loads_on"])
    assert (
        len(
            {
                name[0]
                for name in first.replace("(", " ").split()
                if name[0] in "ab" and name[1:2].isdigit()
            }
        )
        == 1
    )
    assert float(item.values["variance_explained_pct"]) > 60  # type: ignore[arg-type]


def test_independent_columns_have_no_components_beyond_chance() -> None:
    rng = np.random.default_rng(5)
    frame = pd.DataFrame(rng.normal(size=(300, 5)), columns=list("abcde"))
    schema, shape = fx.prepare(frame)
    item = run_components(frame, schema, shape, config=CONFIG)
    assert item.status == "no_lift"
    assert item.sentence.startswith("No components beyond chance")


def test_components_need_three_columns() -> None:
    frame = _factors().iloc[:, :2]
    schema, shape = fx.prepare(frame)
    assert run_components(frame, schema, shape, config=CONFIG).status == "not_run"


def test_a_segment_profile_names_what_sets_it_apart_and_its_share_of_the_money() -> None:
    frame = fx.three_blobs()
    frame["rev"] = frame["a"] + 20.0  # segments hold about 20 / 28 / 20 per row
    schema, shape = fx.prepare(frame)
    item = run_segments(frame, schema, shape, config=CONFIG, roles={"rev": "amount"})
    assert item.status == "ok", item.sentence
    shares = [float(r["share of rev (%)"]) for r in item.table]  # type: ignore[arg-type]
    assert max(shares) == pytest.approx(100 * 28 / 68, abs=2.0)
    assert sum(shares) == pytest.approx(100.0, abs=1e-6)
    assert all(r["stands_out_by"] for r in item.table)
    assert "stands out by" in item.sentence
    assert "% of rev" in item.sentence


@pytest.mark.parametrize("task", ["regression", "classification"])
def test_nearest_neighbours_are_on_the_menu_until_the_table_is_large(task: str) -> None:
    assert "knn" in {f.key for f in families(task, CONFIG, n_rows=500)}
    big = CONFIG.grids.knn_max_rows + 1
    assert "knn" not in {f.key for f in families(task, CONFIG, n_rows=big)}
    assert "svm" not in {f.key for f in families(task, CONFIG, n_rows=big)}
