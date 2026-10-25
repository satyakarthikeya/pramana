"""The planner's closed-menu forecast request: a column and a horizon, nothing else."""

from __future__ import annotations

from pathlib import Path

import pytest

from pramana.analysis import load_config
from pramana.analysis.planner import AnalysisSpec
from pramana.analysis.planner.planner import _SYSTEM, _SYSTEM_FORECAST
from pramana.contracts import ClaimType, Direction, render_forecast_claim
from pramana.verification.admissibility import screen
from pramana.verification.config import ClaimsConfig
from tests.fixtures.config import load_pinned_config
from tests.unit.analysis.test_planner import Script, finance, plan, spec


@pytest.fixture()
def hyp():
    base = load_config().hypotheses
    proposer = {**base.proposer.model_dump(), "engine": "planner"}
    return type(base).model_validate({**base.model_dump(), "proposer": proposer})


@pytest.fixture(autouse=True)
def _artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pramana.analysis.planner.planner.DATA_DIR", tmp_path)


def _on(monkeypatch: pytest.MonkeyPatch, enabled: bool = True) -> None:
    config = load_pinned_config()
    config = config.model_copy(update={"claims": ClaimsConfig(forecast_enabled=enabled)})
    monkeypatch.setattr(
        "pramana.analysis.planner.planner.forecast_offer", lambda: config if enabled else None
    )


def test_a_forecast_request_is_rendered_by_code_from_a_column_and_a_horizon(
    hyp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _on(monkeypatch)
    frame = finance(60)
    script = Script(spec(forecast_requests=[{"column": "revenue", "horizon": 2}]))
    outcome = plan(frame, hyp, script)
    assert [c.claim_type for c in outcome.candidates] == [ClaimType.FORECAST]
    candidate = outcome.candidates[0]
    assert candidate.variables == ["month", "revenue"]
    assert candidate.asserted_direction is Direction.POSITIVE
    assert candidate.forecast is not None and candidate.forecast.horizon == 2
    assert candidate.claim == render_forecast_claim("revenue", candidate.forecast)
    assert not {"p_value", "q_value", "verdict"} & set(candidate.analysis_evidence)
    assert screen(candidate, list(frame.columns), forecast_enabled=True).admissible
    assert outcome.record.accepted_claims[0].claim_type == "forecast"
    # the offer is in the prompt, with the limit of what it tests
    system = script.seen[0][0].content
    assert "forecast_requests" in system and "never what the next periods will be" in system


def test_with_the_flag_off_the_prompt_is_unchanged_and_a_request_is_dropped(
    hyp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _on(monkeypatch, enabled=False)
    script = Script(spec(forecast_requests=[{"column": "revenue", "horizon": 2}]))
    outcome = plan(finance(60), hyp, script)
    assert outcome.candidates == []
    drop = outcome.record.dropped[0]
    assert drop.what == "claim" and "not switched on" in drop.reason
    system = script.seen[0][0].content
    assert "forecast_requests" not in system
    assert system.startswith(_SYSTEM.split("__CLAIMS__")[0][:200])


def test_a_request_may_carry_only_a_column_and_a_horizon() -> None:
    with pytest.raises(ValueError):
        AnalysisSpec.model_validate(
            {
                "shape_confirmation": {"verdict": "confirm", "note": ""},
                "forecast_requests": [
                    {"column": "revenue", "horizon": 2, "method": "holt_winters"}
                ],
            }
        )
    with pytest.raises(ValueError):
        AnalysisSpec.model_validate(
            {
                "shape_confirmation": {"verdict": "confirm", "note": ""},
                "forecast_requests": [{"column": "revenue", "horizon": 2, "claim": "it is proven"}],
            }
        )
    assert "__FORECASTS__" in _SYSTEM_FORECAST


def test_bad_requests_are_dropped_with_reasons(hyp, monkeypatch: pytest.MonkeyPatch) -> None:
    _on(monkeypatch)
    script = Script(
        spec(
            forecast_requests=[
                {"column": "nope", "horizon": 2},
                {"column": "region", "horizon": 2},
                {"column": "revenue", "horizon": 20},
            ]
        )
    )
    outcome = plan(finance(60), hyp, script)
    assert outcome.candidates == []
    reasons = {d.reason_code for d in outcome.record.dropped}
    assert (
        reasons <= {"unknown_column", "wrong_shape", "invalid_fields"}
        and len(outcome.record.dropped) == 3
    )


def test_the_model_cannot_pick_the_method_it_is_not_in_the_menu() -> None:
    from pramana.analysis.planner.models import PlannedForecastRequest

    assert set(PlannedForecastRequest.model_fields) == {"column", "horizon"}


def test_a_request_is_dropped_when_the_exploration_periods_are_too_few_to_choose_a_baseline(
    hyp, monkeypatch: pytest.MonkeyPatch
) -> None:
    _on(monkeypatch)
    script = Script(spec(forecast_requests=[{"column": "revenue", "horizon": 2}]))
    outcome = plan(finance(26), hyp, script)
    assert outcome.candidates == []
    assert "too few to choose a method and a baseline" in outcome.record.dropped[0].reason
