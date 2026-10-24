"""The planner, driven by scripted model replies (tests only; no provider is called)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from pramana.analysis import infer_schema, load_config
from pramana.analysis.exploration import explore_and_propose
from pramana.analysis.hypotheses.llm_proposer import ProposerUnavailable
from pramana.analysis.measured import load_measured_config
from pramana.analysis.planner import AnalysisSpec
from pramana.analysis.planner.config import PlannerConfig, load_planner_config
from pramana.analysis.planner.planner import run_planner
from pramana.analysis.shape import DataShape, classify_shape
from pramana.common.llm_client import ChatMessage, Completion
from pramana.contracts import CandidateInsight, ClaimType
from pramana.verification.admissibility import screen

PLANNER = load_planner_config()
NO_MEASURED = load_measured_config().model_copy(update={"enabled": False})
SHAPE_OK = {"verdict": "confirm", "note": "monthly panel"}


def finance(n_months: int = 48) -> pd.DataFrame:
    """48 months x 3 regions: a rising revenue with a December peak; profit = revenue - cost."""
    rng = np.random.default_rng(5)
    rows = []
    for m in range(n_months):
        stamp = pd.Timestamp("2021-01-01") + pd.DateOffset(months=m)
        for region, offset in (("North", 20.0), ("South", 0.0), ("East", -15.0)):
            revenue = 200 + 2.0 * m + offset + (40.0 if stamp.month == 12 else 0.0)
            revenue += rng.normal(0, 4)
            cost = 0.6 * revenue + rng.normal(0, 6)
            rows.append(
                {
                    "month": stamp,
                    "region": region,
                    "revenue": revenue,
                    "cost": cost,
                    "profit": revenue - cost,
                    "units": 0.2 * revenue + rng.normal(0, 14),
                }
            )
    return pd.DataFrame(rows)


def yearly() -> pd.DataFrame:
    rng = np.random.default_rng(6)
    rows = [
        {"year": 2000 + y, "region": r, "revenue": 100 + 3 * y + rng.normal(0, 3)}
        for y in range(24)
        for r in ("North", "South", "East")
    ]
    return pd.DataFrame(rows)


class Script:
    """Replies in order; remembers what the model was shown."""

    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.seen: list[list[ChatMessage]] = []

    def __call__(self, messages: Sequence[ChatMessage]) -> Completion:
        self.seen.append(list(messages))
        reply = self.replies.pop(0)
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return Completion(content=text, input_tokens=900, output_tokens=120)


def spec(**parts: Any) -> dict[str, Any]:
    return {"shape_confirmation": SHAPE_OK, **parts}


def claim(kind: str, x: str, y: str, direction: str | None = None, ref: str | None = None):
    return {"claim_type": kind, "variables": [x, y], "direction": direction, "reference_group": ref}


@pytest.fixture()
def hyp():
    base = load_config().hypotheses
    proposer = {**base.proposer.model_dump(), "engine": "planner"}
    return type(base).model_validate({**base.model_dump(), "proposer": proposer})


@pytest.fixture(autouse=True)
def _artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("pramana.analysis.planner.planner.DATA_DIR", tmp_path)


def plan(frame: pd.DataFrame, hyp, script: Script, *, planner: PlannerConfig = PLANNER, **kwargs):
    schema = infer_schema(frame, load_config().schema_inference)
    shape = classify_shape(frame, schema)
    return run_planner(
        frame,
        schema,
        shape,
        config=hyp,
        run_id=uuid4(),
        dataset_ref="ref",
        chat=script,
        planner_config=planner,
        measured_config=kwargs.pop("measured_config", NO_MEASURED),
        **kwargs,
    )


def test_the_fixture_is_a_monthly_panel() -> None:
    frame = finance()
    shape = classify_shape(frame, infer_schema(frame, load_config().schema_inference))
    assert shape.shape is DataShape.PANEL and shape.period == "month"
    assert shape.time_column == "month" and shape.full_cycles == 4


def test_a_valid_plan_gives_time_claims_rendered_by_code_and_a_driver_request(hyp) -> None:
    script = Script(
        spec(
            measured_requests=[
                {
                    "task": "driver_regression",
                    "target": "revenue",
                    "features": ["units", "region"],
                    "reason_code": "suspected_driver",
                }
            ],
            claims=[
                claim("trend", "month", "revenue", "positive"),
                claim("seasonality", "month", "revenue"),
                claim("period_change", "month", "revenue", "positive"),
            ],
            narrative_focus=["period_change:revenue"],
        )
    )
    frame = finance()
    outcome = plan(frame, hyp, script)
    by_type = {c.claim_type: c for c in outcome.candidates}
    assert set(by_type) == {ClaimType.TREND, ClaimType.SEASONALITY, ClaimType.PERIOD_CHANGE}
    assert by_type[ClaimType.SEASONALITY].claim == "revenue tends to differ by month of the year"
    assert by_type[ClaimType.PERIOD_CHANGE].claim == (
        "revenue in the latest period tends to be higher than in the period before"
    )
    assert by_type[ClaimType.TREND].claim == "revenue is positively associated with month"
    columns = list(frame.columns)
    for candidate in outcome.candidates:
        assert screen(candidate, columns).admissible
        assert candidate.variables == ["month", "revenue"]
        assert not {"p_value", "q_value", "verdict"} & set(candidate.analysis_evidence)
    assert [r.task for r in outcome.measured_requests] == ["driver_regression"]
    assert outcome.measured_requests[0].features == ["units", "region"]
    assert outcome.record.dropped == []
    summary = outcome.exploration_summary
    assert summary.engine == "planner" and summary.proposed == 3 and summary.turns == 1
    assert (
        summary.plan == outcome.record
        and summary.measured_requests == outcome.record.accepted_measured
    )
    assert outcome.narrative_focus == summary.narrative_focus
    # exact figures were offered, so the id above was a valid choice
    assert outcome.record.accepted_focus == ["period_change:revenue"]


def test_parts_that_break_the_rules_are_dropped_with_recorded_reasons(hyp) -> None:
    bad = spec(
        measured_requests=[
            {"task": "driver_regression", "target": "profit", "features": ["revenue", "cost"]},
            {"task": "driver_regression", "target": "revenue", "features": ["nope"]},
            {"task": "driver_regression", "target": "revenue", "features": ["units"]},
            {"task": "driver_regression", "target": "revenue", "features": ["units"]},
            {"task": "driver_classification", "target": "revenue", "features": ["units"]},
        ],
        claims=[
            claim("trend", "month", "not_a_column", "positive"),
            claim("group_difference", "revenue", "cost"),
            claim("correlation", "revenue", "region"),
            claim("trend", "revenue", "cost", "positive"),
            claim("seasonality", "month", "revenue", "positive"),
            claim("correlation", "units", "revenue", "positive"),
            claim("correlation", "units", "revenue", "positive"),
            claim("correlation", "cost", "revenue", "positive"),
            claim("correlation", "cost", "units", "positive"),
        ],
        narrative_focus=["made_up:id", "period_change:revenue", "period_change:revenue"],
    )
    cfg = PLANNER.model_copy(update={"max_claims": 2, "max_narrative_focus": 5})
    outcome = plan(finance(), hyp, Script(bad), planner=cfg)
    codes = {(d.what, d.item.split("(")[0], d.reason_code) for d in outcome.record.dropped}
    reasons = {d.reason_code for d in outcome.record.dropped if d.what == "claim"}
    assert ("claim", "trend", "unknown_column") in codes
    assert ("claim", "group_difference", "wrong_shape") in codes
    assert ("claim", "correlation", "wrong_shape") in codes  # region is not numeric
    assert ("claim", "seasonality", "invalid_fields") in codes
    # units~revenue, cost~revenue and cost~units restate how the table is built (and the
    # repeated pair is dropped for the same reason before it can be a duplicate)
    assert ("claim", "correlation", "bookkeeping") in codes
    assert ("claim", "correlation", "over_budget") in codes
    assert reasons >= {"unknown_column", "wrong_shape", "invalid_fields", "duplicate"}
    assert len(outcome.candidates) == 2
    requests = {
        (d.reason_code, d.item) for d in outcome.record.dropped if d.what == "measured_request"
    }
    kinds = [code for code, _ in requests]
    assert "leakage" in kinds and "unknown_column" in kinds and "duplicate" in kinds
    assert "wrong_shape" in kinds  # a numeric column cannot be a class target
    leak = next(d for d in outcome.record.dropped if d.reason_code == "leakage")
    assert "profit" in leak.reason or "revenue" in leak.reason
    assert [(r.target, r.features) for r in outcome.measured_requests] == [("revenue", ["units"])]
    focus = {(d.reason_code, d.item) for d in outcome.record.dropped if d.what == "narrative_focus"}
    assert ("unknown_item", "made_up:id") in focus


def test_measured_requests_over_budget_are_dropped(hyp) -> None:
    asks = [
        {"task": "driver_regression", "target": "revenue", "features": ["units"]},
        {"task": "segments"},
        {"task": "anomalies"},
    ]
    cfg = PLANNER.model_copy(update={"max_measured_requests": 2})
    outcome = plan(finance(), hyp, Script(spec(measured_requests=asks)), planner=cfg)
    assert [r.task for r in outcome.measured_requests] == ["driver_regression", "segments"]
    assert [d.reason_code for d in outcome.record.dropped] == ["over_budget"]


def test_a_seasonality_claim_on_a_yearly_table_is_dropped(hyp) -> None:
    frame = yearly()
    outcome = plan(
        frame,
        hyp,
        Script(
            spec(
                claims=[
                    claim("seasonality", "year", "revenue"),
                    claim("period_change", "year", "revenue", "positive"),
                ]
            )
        ),
    )
    dropped = {d.item.split("(")[0]: d for d in outcome.record.dropped}
    assert dropped["seasonality"].reason_code == "wrong_shape"
    assert "monthly or quarterly" in dropped["seasonality"].reason
    assert [c.claim_type for c in outcome.candidates] == [ClaimType.PERIOD_CHANGE]


def test_a_period_change_claim_on_a_one_value_per_period_table_is_dropped(hyp) -> None:
    frame = finance()
    frame = frame[frame["region"] == "North"].reset_index(drop=True)
    outcome = plan(frame, hyp, Script(spec(claims=[claim("period_change", "month", "revenue")])))
    assert outcome.candidates == []
    assert outcome.record.dropped[0].reason_code == "wrong_shape"


def test_invalid_json_gets_one_repair_turn_then_fails_closed(hyp) -> None:
    good = spec(claims=[claim("trend", "month", "revenue", "positive")])
    repaired = Script("this is not json", good)
    outcome = plan(finance(), hyp, repaired)
    assert outcome.record.repaired and outcome.exploration_summary.turns == 2
    assert len(outcome.candidates) == 1
    assert "not a valid plan" in repaired.seen[1][-1].content

    twice = Script("{", "also {not json")
    with pytest.raises(ProposerUnavailable, match="valid plan"):
        plan(finance(), hyp, twice)
    assert twice.replies == [] and len(twice.seen) == 2


def test_a_reply_with_a_claim_text_field_is_refused(hyp) -> None:
    sneaky = spec(claims=[{**claim("trend", "month", "revenue"), "claim": "revenue always rises"}])
    with pytest.raises(ProposerUnavailable):
        plan(finance(), hyp, Script(sneaky, sneaky))
    with pytest.raises(Exception, match="claim"):
        AnalysisSpec.model_validate(sneaky)
    for extra in ({"p_value": 0.001}, {"verdict": "PASS"}, {"code": "import os"}):
        with pytest.raises(Exception, match="Extra inputs"):
            AnalysisSpec.model_validate(spec(**extra))
    repaired = Script(sneaky, spec(claims=[claim("trend", "month", "revenue", "positive")]))
    outcome = plan(finance(), hyp, repaired)
    assert [c.claim for c in outcome.candidates] == ["revenue is positively associated with month"]


def test_the_shape_can_only_be_flagged_never_changed(hyp) -> None:
    flagged = spec(claims=[claim("seasonality", "month", "revenue")])
    flagged["shape_confirmation"] = {"verdict": "flag", "note": "looks\nlike   a daily table"}
    outcome = plan(finance(), hyp, Script(flagged))
    assert outcome.record.shape == "panel" and outcome.record.shape_confirmation.verdict == "flag"
    assert outcome.record.shape_confirmation.note == "looks like a daily table"
    assert len(outcome.candidates) == 1  # code kept the shape it classified


def test_without_a_key_the_planner_fails_closed_with_no_fallback(
    hyp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    frame = finance()
    schema = infer_schema(frame, load_config().schema_inference)
    with pytest.raises(ProposerUnavailable, match="DEEPSEEK_API_KEY"):
        run_planner(
            frame,
            schema,
            classify_shape(frame, schema),
            config=hyp,
            run_id=uuid4(),
            dataset_ref="r",
        )
    with pytest.raises(ProposerUnavailable):
        explore_and_propose(frame, schema, hyp, dataset_ref="r", run_id=uuid4())


def test_the_model_sees_names_roles_and_figures_but_no_rows(hyp) -> None:
    script = Script(spec())
    frame = finance()
    plan(frame, hyp, script)
    system, user = (m.content for m in script.seen[0])
    assert "untrusted data" in system and "BRIEF_JSON" in user
    brief = json.loads(user.split("\n", 1)[1])
    assert brief["shape"]["shape"] == "panel" and brief["shape"]["time_column"] == "month"
    assert {c["name"] for c in brief["columns"]} >= {"month", "region", "revenue"}
    assert any(f["id"] == "period_change:revenue" for f in brief["exact_figures"])
    assert str(frame["revenue"].iloc[7]) not in user


def test_explore_and_propose_routes_the_planner_engine(hyp) -> None:
    frame = finance()
    schema = infer_schema(frame, load_config().schema_inference)
    outcome = explore_and_propose(
        frame,
        schema,
        hyp,
        dataset_ref="ref",
        run_id=uuid4(),
        chat=Script(spec(claims=[claim("trend", "month", "revenue", "positive")])),
    )
    candidates, summary = outcome
    assert [c.variables for c in candidates] == [["month", "revenue"]]
    assert summary.engine == "planner" and summary.plan is not None
    assert isinstance(candidates[0], CandidateInsight)


# --- PLAN D5: the planner never sees a confirmation row --------------------------


def _tagged_panel() -> pd.DataFrame:
    frame = finance()
    frame.insert(0, "row_tag", [f"tag{i:04d}" for i in range(len(frame))])
    return frame


@pytest.mark.slow
def test_the_planner_sees_no_confirmation_row_or_number(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from pramana.analysis.planner import planner as planner_module
    from pramana.common.config import load_runtime_config
    from pramana.orchestration.analysis_integration import native_analysis_adapters
    from pramana.orchestration.state import PramanaState
    from pramana.orchestration.verification_integration import gate_rows
    from pramana.verification.config import load_config as load_verification_config

    monkeypatch.setenv("PRAMANA_ANALYSIS_ENGINE", "planner")
    monkeypatch.setenv("PRAMANA_MEASURED_ENABLED", "true")
    vconfig = load_verification_config()
    adapters = native_analysis_adapters(data_dir=tmp_path)

    def prepared(frame: pd.DataFrame) -> PramanaState:
        state = PramanaState(
            run_id=uuid4(), runtime=load_runtime_config(), dataset=frame, dataset_ref="up.csv"
        )
        return state.model_copy(update=adapters.prepare(state))

    # Learn which rows the gate will test on, then plant a distinctive extreme in one of them.
    first = prepared(_tagged_panel())
    confirm, _ = gate_rows(first.dataset, first.data_structure, vconfig)
    raw = _tagged_panel()
    planted_tag = confirm["row_tag"].iloc[0]
    raw.loc[raw["row_tag"] == planted_tag, "revenue"] = 1234.5678
    state = prepared(raw)
    confirm, record = gate_rows(state.dataset, state.data_structure, vconfig)
    tags = set(confirm["row_tag"])
    numbers = {
        form for value in confirm["revenue"] for form in (str(float(value)), f"{float(value):.4f}")
    }
    assert planted_tag in tags and 1234.5678 in set(confirm["revenue"])
    assert record is not None and len(tags) > 20

    script = Script(spec(claims=[claim("trend", "month", "revenue", "positive")]))
    monkeypatch.setattr(planner_module, "_default_chat", lambda *_a, **_k: script)
    exact_frames: list[pd.DataFrame] = []
    measured_frames: list[pd.DataFrame] = []
    real_exact, real_measured = planner_module.compute_analysis, planner_module.compute_measured

    def spy_exact(frame: pd.DataFrame, *args: Any, **kwargs: Any) -> Any:
        exact_frames.append(frame.copy())
        return real_exact(frame, *args, **kwargs)

    def spy_measured(frame: pd.DataFrame, *args: Any, **kwargs: Any) -> Any:
        measured_frames.append(frame.copy())
        return real_measured(frame, *args, **kwargs)

    monkeypatch.setattr(planner_module, "compute_analysis", spy_exact)
    monkeypatch.setattr(planner_module, "compute_measured", spy_measured)

    result = adapters.analyze(state)

    assert result["candidate_insights"], "the plan should have produced a candidate"
    assert result["exploration"]["engine"] == "planner"
    assert exact_frames and measured_frames
    for seen in (*exact_frames, *measured_frames):
        assert len(seen) < len(state.dataset)
        assert set(seen["row_tag"]).isdisjoint(tags)
        assert 1234.5678 not in set(seen["revenue"])
        assert set(seen["revenue"]).isdisjoint(set(confirm["revenue"]))
    prompt = " ".join(m.content for call in script.seen for m in call)
    assert "BRIEF_JSON" in prompt
    # the brief's period counts are the exploration rows', not the whole table's
    brief = json.loads(script.seen[0][1].content.split("\n", 1)[1])
    explored_months = exact_frames[0]["month"].nunique()
    assert brief["shape"]["n_periods"] == explored_months
    assert explored_months < state.dataset["month"].nunique()
    assert not any(tag in prompt for tag in tags)
    assert "1234.5678" not in prompt and "1234.57" not in prompt
    assert not any(number in prompt for number in numbers)
    # the tiers were given real exploration rows, and together with the gate's they are the table
    explored = set(exact_frames[0]["row_tag"])
    assert explored and explored.isdisjoint(tags)
    assert len(explored) + len(tags) == len(state.dataset)


def test_a_failed_model_call_fails_closed_and_keeps_the_transcript(
    hyp, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from pramana.common.llm_client import LLMUnavailable

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")

    def refuse(*_a: Any, **_k: Any) -> Completion:
        raise LLMUnavailable("Langfuse authentication failed")

    monkeypatch.setattr("pramana.analysis.planner.planner.complete_chat", refuse)
    frame = finance()
    schema = infer_schema(frame, load_config().schema_inference)
    run_id = uuid4()
    with pytest.raises(ProposerUnavailable, match="unavailable"):
        run_planner(
            frame,
            schema,
            classify_shape(frame, schema),
            config=hyp,
            run_id=run_id,
            dataset_ref="r",
            measured_config=NO_MEASURED,
        )
    assert (tmp_path / "runs" / str(run_id) / "planner_transcript.json").exists()


@pytest.mark.slow
def test_accepted_measured_requests_run_on_the_whole_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The planner's driver request is run, on every row, and reaches the run state."""
    from pramana.analysis.measured import runner as measured_runner
    from pramana.analysis.planner import planner as planner_module
    from pramana.common.config import load_runtime_config
    from pramana.orchestration.analysis_integration import native_analysis_adapters
    from pramana.orchestration.state import PramanaState

    monkeypatch.setenv("PRAMANA_ANALYSIS_ENGINE", "planner")
    adapters = native_analysis_adapters(data_dir=tmp_path)
    frame = finance()
    state = PramanaState(
        run_id=uuid4(), runtime=load_runtime_config(), dataset=frame, dataset_ref="up.csv"
    )
    state = state.model_copy(update=adapters.prepare(state))
    request = {
        "task": "driver_regression",
        "target": "units",
        "features": ["revenue", "cost"],
        "controls": [],
        "reason_code": "suspected_driver",
    }
    script = Script(
        spec(claims=[claim("trend", "month", "revenue", "positive")], measured_requests=[request])
    )
    monkeypatch.setattr(planner_module, "_default_chat", lambda *_a, **_k: script)
    sizes: list[int] = []
    real = measured_runner.compute_measured

    def spy(rows: pd.DataFrame, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get("requests"):
            sizes.append(len(rows))
        return real(rows, *args, **kwargs)

    monkeypatch.setattr(measured_runner, "compute_measured", spy)
    monkeypatch.setattr("pramana.analysis.measured.compute_measured", spy)

    update = adapters.analyze(state)

    assert sizes == [len(frame)], "the requested analysis runs once, on the whole table"
    planned = update["planned_measured"]
    assert [item["kind"] for item in planned["items"]] == ["driver_regression"]
    assert planned["items"][0]["target"] == "units"


def test_the_prompt_steers_time_tables_away_from_latest_month_claims() -> None:
    from pramana.analysis.planner.planner import _SYSTEM

    assert "Avoid period_change on daily, weekly or monthly rows" in _SYSTEM
    assert "seasonality claim" in _SYSTEM and "group_difference of the main amount" in _SYSTEM
