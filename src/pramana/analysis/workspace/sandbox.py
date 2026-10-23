"""A bounded Python workspace: numpy and pandas on a copy of the data, nothing else.

Reuses the verification sandbox's static import policy, then runs the program in a
subprocess with a timeout, a memory cap on POSIX and a minimal environment. The program
sees the table as `df` and returns results by calling `emit(value)`; the printed output
is bounded before the model ever reads it.

What protects it, in layers: imports are whitelisted and escape builtins refused (static);
file helpers and module-hopping names (`pd.io`, `.os`, `.sys`) are refused by name (static);
and inside the child process a runtime audit hook refuses every write, every read outside
the Python install and the working folder, every process spawn and every socket (runtime).
That blocks the known ways around the static checks, and tests keep them blocked.

What it is not: a proof. A program that finds a way past all three layers still shares the
server's filesystem in the in-process API container, so the tool ships OFF
(`workspace.sandbox.enabled`). Turn it on only for a single-user install, or inside the
isolated worker container (read-only filesystem, no network).

Nothing computed here is evidence. The gateway recomputes every claim from the table.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict

from pramana.analysis.workspace.config import SandboxConfig
from pramana.verification.executor.policy import ImportPolicyViolation, check_imports

_SENTINEL = "__PRAMANA_WORKSPACE_RESULT__"
_PASSTHROUGH_ENV = ("SYSTEMROOT", "PATH", "LD_LIBRARY_PATH", "PYTHONHOME")
_THREAD_CAPS = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)

#: Attribute names that read or write files, refused wherever they appear.
_FILE_ACCESS_PREFIXES = ("read_", "to_")
_FILE_ACCESS_ALLOWED_TO = frozenset(
    {
        "to_numpy",
        "to_list",
        "tolist",
        "to_dict",
        "to_frame",
        "to_string",
        "to_period",
        "to_timestamp",
        "to_datetime",
        "to_numeric",
        "to_timedelta",
        "to_series",
        "to_records",
        "to_markdown",
        "to_flat_index",
        "to_pydatetime",
    }
)
_FILE_ACCESS_NAMES = frozenset(
    {
        "load",
        "loadtxt",
        "genfromtxt",
        "fromfile",
        "fromregex",
        "tofile",
        "save",
        "savez",
        "savez_compressed",
        "savetxt",
        "memmap",
        "DataSource",
        "ctypeslib",
    }
)
#: Module-hopping attribute names: `pd.io.common.os.system(...)` needs none of the file
#: helpers above, so the way through to `os`, `sys` and the IO internals is refused too.
_MODULE_HOPS = frozenset({"io", "os", "sys", "subprocess", "shutil", "testing", "compat"})

_HARNESS = """
import json, math, os, sys
import numpy as np
import pandas as pd

df = pd.read_pickle(__FRAME__)
_emitted = []

_PREFIXES = tuple(
    os.path.normcase(os.path.realpath(p))
    for p in {sys.prefix, sys.base_prefix, sys.exec_prefix, os.getcwd()}
)
_BLOCKED_EVENTS = (
    "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.fork", "os.forkpty",
    "os.kill", "os.killpg", "os.listdir", "os.scandir", "os.remove", "os.rename",
    "os.replace", "os.mkdir", "os.rmdir", "os.chmod", "os.chown", "os.link",
    "os.symlink", "os.truncate", "os.putenv", "os.unsetenv", "os.startfile",
    "subprocess.", "socket.", "shutil.", "ctypes.", "urllib.", "webbrowser.", "pty.",
    "winreg.", "msvcrt.", "sqlite3.", "glob.",
)
_BLOCKED_IMPORTS = {
    "subprocess", "socket", "ctypes", "http", "ftplib", "smtplib", "multiprocessing",
    "webbrowser", "pty", "winreg", "msvcrt", "sqlite3", "urllib.request", "_winapi",
}

def _audit(event, args):
    if event.startswith(_BLOCKED_EVENTS):
        raise PermissionError("blocked in the workspace: " + event)
    if event == "import" and args[0] in _BLOCKED_IMPORTS:
        raise PermissionError("blocked in the workspace: import " + str(args[0]))
    if event == "open":
        path, mode, flags = args[0], args[1] or "r", args[2] or 0
        writing = any(c in str(mode) for c in "wax+") or bool(
            flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC)
        )
        if isinstance(path, int):
            return
        where = os.path.normcase(os.path.realpath(os.fsdecode(path)))
        if writing or not where.startswith(_PREFIXES):
            raise PermissionError("blocked in the workspace: open " + str(path))

sys.addaudithook(_audit)

def emit(value):
    _emitted.append(value)

def _clean(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, (pd.Series, pd.Index)):
        return _clean(value.tolist())
    if isinstance(value, pd.DataFrame):
        return _clean(value.to_dict(orient="list"))
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(v) for v in value]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    return str(value)

_namespace = {"df": df, "np": np, "pd": pd, "emit": emit, "__name__": "__workspace__"}
with open(__SOURCE__, encoding="utf-8") as _handle:
    _code = compile(_handle.read(), "workspace_program", "exec")
exec(_code, _namespace)
sys.stdout.write("\\n" + __SENTINEL__ + json.dumps(_clean(_emitted), allow_nan=False) + "\\n")
"""


class PythonResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    output: Any = None
    stdout: str = ""
    error: str | None = None
    duration_ms: int = 0


def _failed(reason: str, started: float) -> PythonResult:
    return PythonResult(
        ok=False, error=reason, duration_ms=int((time.monotonic() - started) * 1000)
    )


def check_workspace_source(source: str, allowed_imports: list[str]) -> None:
    """Refuse the program unless it passes the import policy and touches no file helper."""
    check_imports(source, allowed_imports)
    for node in ast.walk(ast.parse(source)):
        name: str | None = None
        if isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                _refuse_file_access(alias.name, node)
            for part in (node.module or "").split("."):
                _refuse_file_access(part, node)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for part in alias.name.split("."):
                    _refuse_file_access(part, node)
        if name is not None:
            _refuse_file_access(name, node)


def _refuse_file_access(name: str, node: ast.AST) -> None:
    banned = (
        name in _FILE_ACCESS_NAMES
        or name in _MODULE_HOPS
        or (name.startswith(_FILE_ACCESS_PREFIXES) and name not in _FILE_ACCESS_ALLOWED_TO)
    )
    if banned:
        raise ImportPolicyViolation(
            f"line {getattr(node, 'lineno', '?')}: {name!r} reads or writes files. "
            "The workspace sees the table as `df` and has no file access."
        )


def _memory_cap(limit_mb: int) -> dict[str, Any]:
    try:
        import resource
    except ImportError:  # pragma: no cover -- Windows
        return {}
    limit = limit_mb * 1024 * 1024

    def apply() -> None:  # pragma: no cover -- runs in the forked child
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))  # type: ignore[attr-defined]

    return {"preexec_fn": apply}


def run_python(source: str, frame: pd.DataFrame, config: SandboxConfig) -> PythonResult:
    """Run `source` on a copy of `frame`; every failure is a result, never an exception."""
    started = time.monotonic()
    if not config.enabled:
        return _failed("the Python workspace is switched off on this server", started)
    try:
        check_workspace_source(source, config.allowed_imports)
    except ImportPolicyViolation as violation:
        return _failed(f"refused before running: {violation}", started)
    with tempfile.TemporaryDirectory(prefix="pramana-workspace-") as directory:
        work = Path(directory)
        source_path, frame_path = work / "program.py", work / "frame.pkl"
        source_path.write_text(source, encoding="utf-8")
        frame.to_pickle(frame_path)
        harness = work / "harness.py"
        harness.write_text(
            _HARNESS.replace("__FRAME__", repr(str(frame_path)))
            .replace("__SOURCE__", repr(str(source_path)))
            .replace("__SENTINEL__", repr(_SENTINEL)),
            encoding="utf-8",
        )
        env = {name: os.environ[name] for name in _PASSTHROUGH_ENV if name in os.environ}
        env.update({name: "1" for name in _THREAD_CAPS})
        env.update({"PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"})
        try:
            completed = subprocess.run(  # noqa: S603 -- source passed the policy above
                [sys.executable, str(harness)],
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds,
                env=env,
                cwd=work,
                **_memory_cap(config.max_memory_mb),
            )
        except subprocess.TimeoutExpired:
            return _failed(f"timed out after {config.timeout_seconds}s and was stopped", started)

    elapsed = int((time.monotonic() - started) * 1000)
    if completed.returncode != 0:
        lines = (completed.stderr or "").strip().splitlines()
        return PythonResult(
            ok=False,
            error=f"the program failed: {lines[-1][:300] if lines else 'no error output'}",
            duration_ms=elapsed,
        )
    lines = (completed.stdout or "").splitlines()
    marker = next(
        (i for i in range(len(lines) - 1, -1, -1) if lines[i].startswith(_SENTINEL)), None
    )
    if marker is None:
        return PythonResult(ok=False, error="the program produced no result", duration_ms=elapsed)
    printed = "\n".join(lines[:marker])[-(config.max_output_chars // 2) :]
    try:
        emitted = json.loads(lines[marker][len(_SENTINEL) :])
    except json.JSONDecodeError:
        return PythonResult(ok=False, error="the result was not valid JSON", duration_ms=elapsed)
    text = json.dumps(emitted, separators=(",", ":"))
    if len(text) > config.max_output_chars:
        emitted = {"truncated": True, "preview": text[: config.max_output_chars]}
    return PythonResult(ok=True, output=emitted, stdout=printed, duration_ms=elapsed)
