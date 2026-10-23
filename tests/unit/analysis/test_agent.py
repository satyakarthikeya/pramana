"""The Analyst loop, driven by scripted model replies (tests only; no provider is called)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from pramana.analysis import infer_schema, load_config
from pramana.analysis.exploration import explore_and_propose
from pramana.analysis.hypotheses.llm_proposer import ProposerUnavailable
from pramana.analysis.reader import read_data
from pramana.analysis.workspace import load_workspace_config
from pramana.analysis.workspace.agent import run_agent
from pramana.common.llm_client import ChatMessage, Completion


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(21)
    n = 300
    age = rng.integers(20, 80, n).astype(float)
    return pd.DataFrame(
        {
            "RIDAGEYR": age,
            "RIAGENDR": rng.choice([1.0, 2.0], n),
            "LBXGLU": 80 + age * 0.5 + rng.normal(0, 8, n),
            "noise": rng.normal(size=n),
        }
    )


class Script:
    """Replies in order, remembers what the model was shown."""

    def __init__(self, *replies: object, input_tokens: int = 500, output_tokens: int = 60) -> None:
        self.replies = list(replies)
        self.seen: list[list[ChatMessage]] = []
        self.usage = (input_tokens, output_tokens)

    def __call__(self, messages: Sequence[ChatMessage]) -> Completion:
        self.seen.append(list(messages))
        reply = self.replies.pop(0)
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return Completion(content=text, input_tokens=self.usage[0], output_tokens=self.usage[1])


def tool(name: str, **args: object) -> dict:
    return {"action": "tool", "tool": name, "args": args}


def final(*claims: dict) -> dict:
    return {"action": "final", "claims": list(claims)}


CORR = {
    "claim_type": "correlation",
    "variables": ["RIDAGEYR", "LBXGLU"],
    "direction": "positive",
    "reference_group": None,
}


@pytest.fixture()
def setup(frame: pd.DataFrame, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr("pramana.analysis.workspace.agent.DATA_DIR", tmp_path)
    analysis = load_config()
    schema = infer_schema(frame, analysis.schema_inference)
    return frame, schema, analysis.hypotheses, load_workspace_config(), tmp_path


def _run(setup, script: Script, **kwargs):
    frame, schema, hyp, config, _ = setup
    return run_agent(
        frame,
        schema,
        hyp,
        config,
        dataset_ref="ref",
        run_id=uuid4(),
        brief=read_data(frame, schema),
        chat=script,
        **kwargs,
    )


def test_explores_with_tools_then_proposes_claims_rendered_by_code(setup) -> None:
    script = Script(
        tool("scan_pairs", top=3),
        tool("relate", x="RIDAGEYR", y="LBXGLU"),
        final(CORR),
    )
    outcome = _run(setup, script)
    assert [c.claim for c in outcome.candidates] == [
        "LBXGLU is positively associated with RIDAGEYR"
    ]
    candidate = outcome.candidates[0]
    assert (
        candidate.variables == ["RIDAGEYR", "LBXGLU"]
        and candidate.asserted_direction.value == "positive"
    )
    assert not {"p_value", "q_value", "verdict"} & set(candidate.analysis_evidence)
    summary = outcome.exploration
    assert summary.engine == "agent" and summary.turns == 3 and summary.tool_calls == 2
    assert summary.examined == 3 + 1  # C(3,2) numeric pairs scanned plus one relate
    assert summary.proposed == 1
    assert summary.input_tokens == 1500 and summary.output_tokens == 180
    assert [e.name for e in summary.entries] == ["scan_pairs", "relate"]


def test_the_model_sees_meanings_and_summaries_but_no_rows(setup) -> None:
    script = Script(final())
    _run(setup, script)
    prompt = " ".join(m.content for m in script.seen[0])
    assert "Age at screening" in prompt and "Fasting plasma glucose" in prompt
    assert '"coding":{"1":"Male","2":"Female"}' in prompt
    row_value = str(setup[0]["LBXGLU"].iloc[7])
    assert row_value not in prompt
    assert "scan_pairs" in prompt and "relate" in prompt


def test_claims_that_break_the_rules_are_dropped_not_repaired(setup) -> None:
    bad_column = {**CORR, "variables": ["RIDAGEYR", "not_a_column"]}
    two_group_no_direction = {
        "claim_type": "group_difference",
        "variables": ["RIAGENDR", "LBXGLU"],
        "direction": None,
        "reference_group": None,
    }
    outcome = _run(setup, Script(final(bad_column, two_group_no_direction, CORR, CORR)))
    assert [c.variables for c in outcome.candidates] == [["RIDAGEYR", "LBXGLU"]]


def test_a_model_cannot_smuggle_text_numbers_or_verdicts_into_a_claim(setup) -> None:
    sneaky = {**CORR, "claim": "LBXGLU always rises", "p_value": 0.001}
    with pytest.raises(ProposerUnavailable, match="format twice"):
        _run(setup, Script(final(sneaky), final(sneaky)))


def test_one_malformed_reply_is_corrected_once(setup) -> None:
    script = Script("not json at all", final(CORR))
    outcome = _run(setup, script)
    assert len(outcome.candidates) == 1 and outcome.exploration.turns == 2
    assert "did not match the format" in script.seen[1][-1].content


def test_hard_stops_apply_to_turns_tools_python_and_tokens(setup) -> None:
    # Never finishes: asks for a tool every turn, including after the budget nudge.
    endless = Script(*[tool("describe", column="noise")] * 10)
    with pytest.raises(ProposerUnavailable, match="whole turn budget"):
        _run(setup, endless)
    assert len(endless.seen) == load_workspace_config().agent.max_turns
    assert "Budget reached" in endless.seen[-1][-1].content

    heavy = Script(
        tool("describe", column="noise"), final(CORR), input_tokens=30000, output_tokens=0
    )
    with pytest.raises(ProposerUnavailable, match="whole token budget"):
        _run(setup, heavy)
    assert len(heavy.seen) == 1  # stopped on tokens before a second call


def test_python_steps_are_capped_and_the_model_is_told(setup) -> None:
    config = load_workspace_config().agent
    program = tool("python", code="emit(1)")
    script = Script(*[program] * (config.max_python_runs + 1), final(CORR))
    frame, schema, hyp, workspace, _ = setup
    bigger = workspace.model_copy(
        update={
            "agent": config.model_copy(update={"max_turns": config.max_python_runs + 3}),
            "sandbox": workspace.sandbox.model_copy(update={"enabled": True}),
        }
    )
    outcome = run_agent(frame, schema, hyp, bigger, dataset_ref="ref", run_id=uuid4(), chat=script)
    assert outcome.exploration.python_runs == config.max_python_runs
    assert "Python budget used up" in script.seen[-1][-1].content


def test_tool_results_are_cut_before_the_model_reads_them(setup) -> None:
    frame, schema, hyp, workspace, _ = setup
    tight = workspace.model_copy(
        update={"agent": workspace.agent.model_copy(update={"max_result_chars": 200})}
    )
    script = Script(tool("scan_pairs", top=25), final())
    run_agent(frame, schema, hyp, tight, dataset_ref="ref", run_id=uuid4(), chat=script)
    result = script.seen[1][-1].content
    assert len(result) < 260 and "truncated" in result


def test_the_transcript_is_written_for_audit(setup) -> None:
    run_id_dir = setup[4]
    _run(setup, Script(tool("describe", column="noise"), final()))
    written = list(run_id_dir.glob("runs/*/agent_transcript.json"))
    assert len(written) == 1
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["usage"] == {"input_tokens": 1000, "output_tokens": 120}
    assert [t.get("turn") for t in payload["turns"]][:2] == [1, 1]


def test_without_a_key_the_agent_refuses_instead_of_falling_back(
    setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    frame, schema, hyp, workspace, _ = setup
    with pytest.raises(ProposerUnavailable, match="DEEPSEEK_API_KEY is not set"):
        run_agent(frame, schema, hyp, workspace, dataset_ref="ref", run_id=uuid4())


def test_the_scan_engine_reports_how_many_pairs_it_looked_at(frame: pd.DataFrame) -> None:
    analysis = load_config()
    deterministic = analysis.hypotheses.model_copy(
        update={
            "proposer": analysis.hypotheses.proposer.model_copy(update={"engine": "deterministic"})
        }
    )
    schema = infer_schema(frame, analysis.schema_inference)
    candidates, summary = explore_and_propose(
        frame, schema, deterministic, dataset_ref="ref", run_id=uuid4()
    )
    numeric_pairs = 3 * 2 // 2  # RIDAGEYR, LBXGLU, noise
    group_pairs = 1 * 3  # RIAGENDR against each numeric column
    assert summary.engine == "scan" and summary.examined == numeric_pairs + group_pairs
    assert summary.proposed == len(candidates) >= 1
