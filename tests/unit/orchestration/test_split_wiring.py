"""PLAN D5 wiring: the proposer never sees a confirmation row, and the gate sees only those."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from pramana.common.config import load_runtime_config
from pramana.contracts import TableShape
from pramana.orchestration.analysis_integration import native_analysis_adapters
from pramana.orchestration.state import PramanaState
from pramana.orchestration.verification_integration import gate_rows
from pramana.verification.config import load_config


def _monthly(n_months: int = 48) -> pd.DataFrame:
    rng = np.random.default_rng(9)
    return pd.DataFrame(
        {
            "row_tag": [f"m{i}" for i in range(n_months)],
            "month": pd.date_range("2021-01-01", periods=n_months, freq="MS").astype(str),
            "revenue": 100 + np.cumsum(1 + rng.normal(size=n_months)),
            "cost": 60 + np.cumsum(rng.normal(size=n_months)),
        }
    )


@pytest.mark.parametrize(
    "frame",
    [
        _monthly(),
        pd.DataFrame(
            {
                "row_tag": [f"r{i}" for i in range(200)],
                "x": np.random.default_rng(1).normal(size=200),
                "y": np.random.default_rng(2).normal(size=200),
            }
        ),
    ],
)
def test_the_proposer_sees_no_confirmation_row(
    frame: pd.DataFrame, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[pd.DataFrame] = []

    def capture(frame_: pd.DataFrame, *_: Any, **__: Any) -> Any:
        seen.append(frame_.copy())

        raise RuntimeError("stop after capturing the proposer's input")

    monkeypatch.setattr("pramana.analysis.exploration.explore_and_propose", capture)
    adapters = native_analysis_adapters(data_dir=tmp_path)
    state = PramanaState(
        run_id=uuid4(), runtime=load_runtime_config(), dataset=frame, dataset_ref="upload.csv"
    )
    state = state.model_copy(update=adapters.prepare(state))
    assert state.data_structure is not None
    with pytest.raises(RuntimeError, match="stop after capturing"):
        adapters.analyze(state)

    confirmation, split = gate_rows(state.dataset, state.data_structure, load_config())
    explored = set(seen[0]["row_tag"])
    confirmed = set(confirmation["row_tag"])
    assert explored and confirmed
    assert explored.isdisjoint(confirmed)
    assert len(explored) + len(confirmed) == len(frame)
    assert split is not None and split.n_confirmation == len(confirmed)


def test_a_monthly_table_is_handed_to_the_gate_as_a_time_series(tmp_path: Any) -> None:
    adapters = native_analysis_adapters(data_dir=tmp_path)
    state = PramanaState(
        run_id=uuid4(), runtime=load_runtime_config(), dataset=_monthly(), dataset_ref="upload.csv"
    )
    structure = adapters.prepare(state)["data_structure"]
    assert structure.shape is TableShape.TIME_SERIES
    assert structure.time_column == "month" and structure.period == "month"
