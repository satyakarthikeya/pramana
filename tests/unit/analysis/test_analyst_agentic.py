"""The tool-using analyst: it runs tools, cites their results, and cannot quote anything else."""

from __future__ import annotations

import json
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from pramana.analysis import load_config
from pramana.analysis.analyst.agentic import agentic_read
from pramana.analysis.analyst.facts import associations
from pramana.analysis.workspace import load_workspace_config
from pramana.common.llm_client import Completion
from tests.unit.analysis import measured_fixtures as fx


@pytest.fixture(scope="module")
def table():
    rng = np.random.default_rng(3)
    x = rng.normal(size=120)
    frame = pd.DataFrame(
        {"income": x, "spend": 2 * x + rng.normal(size=120), "age": rng.normal(size=120)}
    )
    schema, _ = fx.prepare(frame)
    return frame, schema


class Script:
    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.sent: list[list] = []

    def __call__(self, messages):
        self.sent.append(list(messages))
        reply = self.replies.pop(0)
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return Completion(content=text, input_tokens=100, output_tokens=50)


def run(table, script, **kw):
    frame, schema = table
    facts = [f for f in [associations(frame, schema, {}, None)] if f]
    return agentic_read(
        frame,
        schema,
        load_config().hypotheses,
        load_workspace_config(),
        facts,
        list(frame.columns),
        [],
        trace_id=uuid4(),
        chat=script,
        **kw,
    ), facts


def tool(name, **args):
    return {"action": "tool", "tool": name, "args": args}


def test_the_agent_runs_a_tool_and_may_quote_only_its_result(table) -> None:
    frame, _ = table
    rho = float(frame["income"].corr(frame["spend"], method="spearman"))
    script = Script(
        tool("relate", x="income", y="spend"),
        {
            "action": "final",
            "paragraphs": [
                {
                    "sources": ["x1"],
                    "text": f"Income and spend go together, with a rank correlation of {rho:.2f} "
                    f"over {len(frame)} rows.",
                },
                {"sources": ["x1"], "text": "Spend rises with income, correlation 0.42."},
            ],
        },
    )
    read, _ = run(table, script)
    assert read.source == "model"
    assert [s.tool for s in read.steps] == ["relate"] and read.steps[0].ok
    assert len(read.paragraphs) == 1 and read.paragraphs_dropped == 1
    assert read.paragraphs[0].fact_ids == ["x1"]


def test_a_paragraph_citing_a_result_it_never_ran_is_refused(table) -> None:
    script = Script(
        {
            "action": "final",
            "paragraphs": [{"sources": ["e9"], "text": "Income goes with spend at 0.80."}],
        },
        {
            "action": "final",
            "paragraphs": [{"sources": ["e9"], "text": "Income goes with spend at 0.80."}],
        },
    )
    with pytest.raises(ValueError, match="number and wording"):
        run(table, script)


def test_a_refused_draft_gets_one_chance_to_rewrite(table) -> None:
    frame, _ = table
    top = associations(*[table[0], table[1], {}, None])
    rho = f"{float(top.table[0]['rank_correlation']):.2f}"
    script = Script(
        {
            "action": "final",
            "paragraphs": [{"sources": ["associations"], "text": "Income drives spend at 0.99."}],
        },
        {
            "action": "final",
            "paragraphs": [
                {"sources": ["associations"], "text": f"Income goes with spend at {rho}."}
            ],
        },
    )
    read, _ = run(table, script)
    assert read.source == "model" and len(read.paragraphs) == 1
    assert "can be shown" in script.sent[1][-1].content


def test_python_is_refused_while_the_sandbox_is_off(table) -> None:
    script = Script(
        tool("python", code="emit(df.income.mean())"),
        {
            "action": "final",
            "paragraphs": [
                {"sources": ["associations"], "text": "Income goes with spend at 0.80."}
            ],
        },
        {
            "action": "final",
            "paragraphs": [
                {"sources": ["associations"], "text": "Income goes with spend at 0.80."}
            ],
        },
    )
    cfg = load_workspace_config()
    assert not cfg.sandbox.enabled, "the committed default keeps the sandbox off"
    with pytest.raises(ValueError):
        run(table, script)
    assert "Unknown tool" in script.sent[1][-1].content, "the agent is told python is unavailable"


def _yearly(revenue_2021: float) -> pd.DataFrame:
    return pd.DataFrame({"year": [2019, 2020, 2021] * 4, "revenue": [90.0, 100.0, revenue_2021] * 4})


def _claim_run(frame: pd.DataFrame):
    from pramana.analysis.analyst.models import Fact

    schema, _ = fx.prepare(frame)
    fact = Fact(id="f1", tier="exact", title="Revenue change", values={"change_pct": 20.0})
    paragraph = {
        "sources": ["f1"],
        "text": "Revenue rose 20% in the latest year.",
        "claims": [{"kind": "change", "measure": "revenue", "granularity": "year",
                    "to_period": "2021", "stated_pct": 20.0}],
    }
    script = Script(
        {"action": "final", "paragraphs": [paragraph]},
        {"action": "final", "paragraphs": [paragraph]},
    )
    return agentic_read(
        frame, schema, load_config().hypotheses, load_workspace_config(), [fact],
        list(frame.columns), [], trace_id=uuid4(), chat=script, time_column="year", additive=True,
    )


def test_a_finding_whose_own_claim_matches_the_table_carries_its_check() -> None:
    read = _claim_run(_yearly(120.0))
    assert read.paragraphs[0].checks[0].status == "matches"


def test_a_finding_whose_own_claim_is_off_is_not_shown() -> None:
    with pytest.raises(ValueError, match="number and wording"):
        _claim_run(_yearly(150.0))
