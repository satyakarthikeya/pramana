"""The analyst's tools and sandbox: known answers, hard limits, and honest counting."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from pramana.analysis import infer_schema, load_config
from pramana.analysis.workspace import (
    ExplorationLedger,
    SandboxConfig,
    Workspace,
    WorkspaceConfig,
    load_workspace_config,
    run_python,
)


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    n = 240
    x = rng.uniform(0, 100, n)
    return pd.DataFrame(
        {
            "x": x,
            "y_strong": x * 2 + rng.normal(0, 3, n),
            "noise": rng.normal(size=n),
            "group": np.where(np.arange(n) % 2 == 0, "a", "b"),
            "shifted": np.where(np.arange(n) % 2 == 0, 10.0, 20.0) + rng.normal(0, 1, n),
            "month": pd.date_range("2020-01-01", periods=n, freq="D"),
            "rising": np.arange(n) * 0.5 + rng.normal(0, 1, n),
        }
    )


def _workspace(frame: pd.DataFrame, *, python: bool = True, **agent: int) -> Workspace:
    analysis = load_config()
    base = load_workspace_config()
    config = base.model_copy(
        update={
            "agent": base.agent.model_copy(update=agent),
            "sandbox": base.sandbox.model_copy(update={"enabled": python}),
        }
    )
    return Workspace(
        frame, infer_schema(frame, analysis.schema_inference), config, analysis.hypotheses
    )


# ---- tools ---------------------------------------------------------------------
def test_relate_recovers_a_planted_relationship_and_a_null(frame: pd.DataFrame) -> None:
    ws = _workspace(frame)
    strong = ws.call("relate", {"x": "x", "y": "y_strong"})
    null = ws.call("relate", {"x": "x", "y": "noise"})
    assert strong.ok and null.ok
    assert strong.output["spearman_rho"] > 0.95 and strong.output["n"] == len(frame)
    assert abs(null.output["spearman_rho"]) < 0.2
    for result in (strong, null):
        assert not {"p_value", "q_value", "verdict"} & set(result.output)


def test_describe_matches_pandas_exactly(frame: pd.DataFrame) -> None:
    ws = _workspace(frame)
    numeric = ws.call("describe", {"column": "x"}).output
    assert numeric["mean"] == round(float(frame["x"].mean()), 6)
    assert numeric["median"] == round(float(frame["x"].median()), 6)
    assert numeric["n"] == len(frame) and numeric["missing"] == 0
    levels = ws.call("describe", {"column": "group"}).output["levels"]
    assert {item["label"]: item["count"] for item in levels} == {"a": 120, "b": 120}


def test_compare_groups_known_answer(frame: pd.DataFrame) -> None:
    out = _workspace(frame).call("compare_groups", {"value": "shifted", "group": "group"}).output
    by_group = {g["group"]: g for g in out["groups"]}
    assert by_group["a"]["n"] == by_group["b"]["n"] == 120
    assert abs(by_group["a"]["median"] - 10) < 0.5 and abs(by_group["b"]["median"] - 20) < 0.5
    assert out["eta_squared"] > 0.9
    assert "no significance" in out["note"]


def test_trend_recovers_a_rising_series(frame: pd.DataFrame) -> None:
    out = _workspace(frame).call("trend", {"value": "rising", "order": "month"})
    assert out.ok, out.error
    assert out.output["kendall_tau_b"] > 0.9


def test_scan_pairs_counts_every_pair_and_ranks_the_planted_one_first(frame: pd.DataFrame) -> None:
    ws = _workspace(frame)
    numeric = ws.schema.usable(
        *[r for r in [__import__("pramana.analysis", fromlist=["ColumnRole"]).ColumnRole.NUMERIC]]
    )
    expected = len(numeric) * (len(numeric) - 1) // 2
    result = ws.call("scan_pairs", {"top": 3})
    assert result.ok and result.examined == expected == result.output["pairs_examined"]
    top = result.output["top"][0]
    assert {top["x"], top["y"]} <= {"x", "y_strong", "shifted", "rising", "noise"}
    assert abs(top["spearman_rho"]) > 0.9
    assert ws.ledger.examined == expected


def test_failures_are_results_and_cost_nothing(frame: pd.DataFrame) -> None:
    ws = _workspace(frame)
    for name, args in [
        ("nope", {}),
        ("relate", {"x": "x"}),
        ("relate", {"x": "x", "y": "missing"}),
        ("relate", {"x": "x", "y": "x"}),
        ("compare_groups", {"value": "group", "group": "x"}),
        ("describe", {"column": "x", "extra": 1}),
    ]:
        result = ws.call(name, args)
        assert not result.ok and result.error and result.examined == 0, (name, args)
    assert ws.ledger.examined == 0
    assert all(not entry.ok for entry in ws.ledger.entries)


def test_examination_budget_refuses_instead_of_overspending(frame: pd.DataFrame) -> None:
    ws = _workspace(frame, max_hypotheses_examined=3)
    refused = ws.call("scan_pairs", {"top": 3})
    assert not refused.ok and "budget" in refused.error
    assert ws.call("relate", {"x": "x", "y": "y_strong"}).ok
    assert ws.examined_budget_left == 2


def test_tool_output_is_json_clean(frame: pd.DataFrame) -> None:
    ws = _workspace(frame)
    broken = frame.copy()
    broken.loc[:5, "x"] = np.nan
    out = _workspace(broken).call("describe", {"column": "x"}).output
    assert out["missing"] == 6
    assert all(not (isinstance(v, float) and math.isnan(v)) for v in out.values())
    assert ws.tool_descriptions()[0]["name"] == "describe"


# ---- sandbox -------------------------------------------------------------------
@pytest.fixture(scope="module")
def sandbox() -> SandboxConfig:
    return load_workspace_config().sandbox.model_copy(update={"enabled": True})


def test_python_computes_on_a_copy_and_returns_clean_json(
    frame: pd.DataFrame, sandbox: SandboxConfig
) -> None:
    before = frame.copy(deep=True)
    result = run_python(
        "emit({'mean': float(df['x'].mean()), 'nan': float('nan'), 'n': int(len(df))})\n"
        "df['x'] = 0\nprint('hello')",
        frame,
        sandbox,
    )
    assert result.ok, result.error
    assert result.output[0]["mean"] == pytest.approx(frame["x"].mean())
    assert result.output[0]["nan"] is None and result.output[0]["n"] == len(frame)
    assert "hello" in result.stdout
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize(
    "code",
    [
        "import os\nemit(os.listdir('.'))",
        "import subprocess",
        "import scipy.stats",
        "from pandas import read_csv\nemit(1)",
        "import pandas as pd\nemit(pd.read_pickle('x'))",
        "emit(open('/etc/passwd').read())",
        "import numpy as np\nemit(np.load('x.npy'))",
        "df.to_csv('leak.csv')",
        "emit(().__class__.__subclasses__())",
        "emit(getattr(df, 'x'))",
        "def broken(:",
    ],
)
def test_forbidden_programs_are_refused_before_running(
    code: str, frame: pd.DataFrame, sandbox: SandboxConfig
) -> None:
    result = run_python(code, frame, sandbox)
    assert not result.ok and "refused before running" in result.error


def test_to_helpers_that_only_convert_are_allowed(
    frame: pd.DataFrame, sandbox: SandboxConfig
) -> None:
    result = run_python(
        "emit(df['x'].head(3).to_list()); emit(df[['x']].to_numpy().shape)", frame, sandbox
    )
    assert result.ok, result.error


def test_timeout_and_crash_and_missing_result_are_failures(frame: pd.DataFrame) -> None:
    quick = SandboxConfig(
        enabled=True,
        timeout_seconds=2,
        max_memory_mb=1024,
        max_output_chars=4000,
        allowed_imports=["numpy", "pandas"],
    )
    slow = run_python("while True:\n    pass", frame, quick)
    assert not slow.ok and "timed out" in slow.error
    # Importing pandas in a fresh process takes seconds, so only the hang uses a short limit.
    patient = quick.model_copy(update={"timeout_seconds": 30})
    crash = run_python("emit(1 / 0)", frame, patient)
    assert not crash.ok and "division by zero" in crash.error
    assert run_python("x = 1", frame, patient).output == []


def test_output_is_bounded_before_the_model_reads_it(frame: pd.DataFrame) -> None:
    small = SandboxConfig(
        enabled=True,
        timeout_seconds=20,
        max_memory_mb=1024,
        max_output_chars=300,
        allowed_imports=["numpy", "pandas"],
    )
    result = run_python("emit(list(range(5000)))", frame, small)
    assert result.ok and result.output["truncated"] is True
    assert len(result.output["preview"]) <= 300


def test_python_through_the_workspace_is_counted_but_examines_nothing(frame: pd.DataFrame) -> None:
    ws = _workspace(frame)
    ok = ws.call("python", {"code": "emit(int(df['x'].nunique()))"})
    assert ok.ok and ok.output["emitted"] == [len(frame)] and ok.examined == 0
    bad = ws.call("python", {"code": "import os"})
    assert not bad.ok
    assert ws.ledger.python_runs == 2 and ws.ledger.examined == 0


def test_ledger_totals_stay_exact_past_the_entry_cap() -> None:
    ledger = ExplorationLedger()
    for _ in range(250):
        ledger.add(
            ledger.next_id(),
            kind="tool",
            name="relate",
            args={},
            ok=True,
            output="x",
            examined=1,
            duration_ms=0,
        )
    assert ledger.examined == 250 and ledger.tool_calls == 250 and len(ledger.entries) == 200


def test_workspace_config_is_validated() -> None:
    with pytest.raises(ValueError):
        WorkspaceConfig.model_validate({"sandbox": {}, "agent": {}})


# ---- the reviewer's working bypasses of the static checks, kept as regression tests ------
BYPASSES = {
    "list a directory": "emit(pd.io.common.os.listdir('.')[:3])",
    "read a file": "h = pd.io.common.get_handle(SECRET, 'r')\nemit(h.handle.read())",
    "run a command": "emit(pd.io.common.os.system('echo pwned'))",
    "write a file": (
        "import pandas.io.common as c\n"
        "with c.get_handle('pwn.txt', 'w') as h:\n    h.handle.write('x')\nemit('wrote')"
    ),
    "network": "emit(pd.io.common.urlopen('http://127.0.0.1:9/').read())",
}


@pytest.fixture()
def secret(tmp_path) -> str:
    """A file outside the program's own folder, like another user's dataset."""
    target = tmp_path / "other_users_data.csv"
    target.write_text("private,values\n1,2\n", encoding="utf-8")
    return target.as_posix()


@pytest.mark.parametrize("name", list(BYPASSES))
def test_module_hopping_bypasses_are_refused(
    name: str, frame: pd.DataFrame, sandbox: SandboxConfig, secret: str
) -> None:
    result = run_python(BYPASSES[name].replace("SECRET", repr(secret)), frame, sandbox)
    assert not result.ok and "refused before running" in result.error, result


@pytest.mark.parametrize(
    "code",
    [
        # Reach the dangerous call without any name the static check knows about.
        "import numpy\nf = numpy.core.multiarray.__dict__\nemit(1)",
        "emit([c for c in ().__class__.__mro__])",
        "emit(getattr(np, 'load'))",
    ],
)
def test_other_routes_are_refused_statically(
    code: str, frame: pd.DataFrame, sandbox: SandboxConfig
) -> None:
    assert not run_python(code, frame, sandbox).ok


def test_runtime_hook_stops_file_process_and_network_even_if_static_checks_were_bypassed(
    frame: pd.DataFrame, sandbox: SandboxConfig, monkeypatch: pytest.MonkeyPatch, secret: str
) -> None:
    # Disable the static layer to prove the runtime layer holds on its own.
    monkeypatch.setattr(
        "pramana.analysis.workspace.sandbox.check_workspace_source", lambda *_a: None
    )
    for name, code in BYPASSES.items():
        result = run_python(code.replace("SECRET", repr(secret)), frame, sandbox)
        assert not result.ok, (name, result.output)
        assert "blocked in the workspace" in (result.error or ""), (name, result.error)
    # open() itself is a builtin the static policy refuses; here the runtime layer must too.
    result = run_python(f"emit(open({secret!r}).read())", frame, sandbox)
    assert not result.ok and "blocked in the workspace" in result.error
    # ...while the program's own folder (its copy of the table) stays readable.
    own = run_python("emit(len(open('frame.pkl', 'rb').read()) > 0)", frame, sandbox)
    assert own.ok and own.output == [True]


def test_the_python_tool_is_off_unless_switched_on(frame: pd.DataFrame) -> None:
    ws = _workspace(frame, python=False)
    assert "python" not in [tool["name"] for tool in ws.tool_descriptions()]
    refused = ws.call("python", {"code": "emit(1)"})
    assert not refused.ok and "Unknown tool" in refused.error
    off = run_python("emit(1)", frame, load_workspace_config().sandbox)
    assert not off.ok and "switched off" in off.error
    assert load_workspace_config().sandbox.enabled is False  # the shipped default


def test_describe_and_missingness_never_touch_excluded_columns() -> None:
    rng = np.random.default_rng(2)
    n = 120
    frame = pd.DataFrame(
        {
            "measure": rng.normal(size=n),
            "other": rng.normal(size=n),
            "person_id": [f"user{i}@example.com" for i in range(n)],
            "constant": np.ones(n),
        }
    )
    ws = _workspace(frame)
    assert not ws.call("describe", {"column": "person_id"}).ok
    names = [c["column"] for c in ws.call("missingness", {}).output["columns"]]
    assert "person_id" not in names and "measure" in names
