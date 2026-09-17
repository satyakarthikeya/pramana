"""The sandboxed runner -- where "fail-closed" stops being a slogan.

Everything in this module exists to make one sentence true: **no path from a failed,
slow, silent, malformed or fabricated execution reaches a usable result.** Not "is
unlikely to"; there is no branch that returns `ok=True` without every check below
having passed.

The checks, and what each one is for
------------------------------------
1. **Static import policy**, before a subprocess exists at all. A violation caught at
   runtime has already run the lines above it.
2. **Subprocess isolation with a timeout.** Generated code runs in a separate
   interpreter, so an infinite loop is killed rather than waited on and a segfault
   takes down a process we own rather than the gateway.
3. **Required keys.** A payload missing a field is a partial result, and a partial
   result cannot produce a complete proof object (AGENTS.md 3.6).
4. **A p-value of exactly zero is refused.** `permutation_test` add-one floors at
   `1/(B+1)`, so zero is arithmetically impossible from the vetted path. Seeing one
   proves the number came from somewhere else. **A non-finite effect size is refused**
   for a related reason: `json.loads` accepts `NaN`, every comparison against NaN is
   False, and the gate's magnitude check is a comparison -- so a NaN effect would pass
   the check it never took.
5. **The effect metric must be a vetted gating metric.** An unrecognised name would
   otherwise reach the gate, which would have no band for it.
6. **The provenance stamp must verify.** This is the check the import whitelist cannot
   perform: code using only numpy and pandas can hand-roll a shuffle loop, or call
   `DataFrame.corr(method="spearman")` which needs no scipy at all, and return a number
   that never went near `permutation_test`. The stamp is an HMAC over the numbers
   themselves under a nonce this process generated, so a result that did not come from
   the audited function cannot carry a valid one.
7. **The effect size must BE the stamped statistic.** The stamp covers `statistic`, not
   `effect_size`, and the gate decides NEGLIGIBLE and REFUTED on `effect_size`. In every
   vetted test the two are the same number -- the permutation statistic is the gating
   metric -- so requiring equality puts the effect under the stamp without a second
   HMAC. An effect that differs from the statistic was written by something other than
   the audited function.
8. **`n_permutations` and `seed` must match the run's config.** A stamp proves the
   numbers came from `permutation_test`; it does not prove the test was the one this
   run promised. Ten resamples produce a genuinely stamped p-value whose floor is
   0.09, and a private seed produces a result nobody can reproduce (AGENTS.md 3.4).

What retrying may and may not fix
---------------------------------
Only EXECUTION failures are retried (timeout, crash, silence): those can be transient,
a loaded machine or a flaky worker. Validation failures are not retried. A payload with
a forged stamp or a zero p-value is a deterministic property of the code that produced
it, and running it again would only produce the same forged stamp more slowly. After
`max_retries` the failure is permanent for that insight.

A note on the memory cap, stated plainly because the report should not overclaim
-------------------------------------------------------------------------------
`max_memory_mb` is enforced with `RLIMIT_AS` on POSIX. On Windows there is no
equivalent available to a plain subprocess, so on a Windows dev machine the cap is
ADVISORY and the real enforcement is the container (`docker/OWNERSHIP.md`, AGENTS.md
4). The timeout is enforced on every platform. This is recorded here rather than left
for someone to discover: an unenforced limit that looks enforced is worse than a
documented gap.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 5
"""

from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

import pramana
from pramana.contracts.enums import EffectMetric
from pramana.verification.config import VerificationConfig
from pramana.verification.executor.policy import ImportPolicyViolation, check_imports
from pramana.verification.stats import provenance

if TYPE_CHECKING:  # pragma: no cover -- import cycle at runtime, Phase 6 owns this model
    from pramana.verification.falsification.generator import FalsificationProgram

_log = logging.getLogger("pramana.verification.executor")

#: Marks the one line of stdout the parent trusts. Generated code is not supposed to
#: print, but a stray print must not be mistaken for the result.
RESULT_SENTINEL = "__PRAMANA_RESULT__"

#: Every field a payload must carry. Anything missing is a partial result.
REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "p_value",
        "effect_size",
        "effect_metric",
        "reported_effect",
        "statistic",
        "n_permutations",
        "seed",
        "provenance",
    }
)

#: The fields the stamp covers, in the order `permutation_test` hashes them. Changing
#: this tuple without changing `stats/permutation.py` breaks every verification, which
#: is exactly the coupling we want: the two must agree or nothing passes.
_STAMPED_FIELDS = ("p_value", "statistic", "n_permutations", "seed")

#: Environment variables the child may inherit. This is what an interpreter needs to
#: BOOT, and nothing more: `SYSTEMROOT` is required by Python's startup on Windows,
#: `PATH` and `LD_LIBRARY_PATH` are how numpy's shared libraries are found on some
#: setups, and `PYTHONHOME` is only ever set for a relocated interpreter. The parent's
#: environment is not the untrusted code's channel to the outside world, so nothing
#: else crosses -- and a variable is copied only when the parent actually has it.
_PASSTHROUGH_ENV: tuple[str, ...] = ("SYSTEMROOT", "PATH", "LD_LIBRARY_PATH", "PYTHONHOME")

#: The trusted harness. It -- not the generated code -- owns every capability the
#: generated code was denied: reading the frame, serialising the result, printing.
#: `pramana.verification.stats` is imported FIRST so `provenance` pops the nonce out of
#: the environment before untrusted code can read it.
_HARNESS = '''import json
import sys

sys.path.insert(0, {src_dir!r})
sys.path.insert(0, {work_dir!r})

import pandas as pd
import pramana.verification.stats  # noqa: F401  -- pops the provenance nonce from env

import falsification_program


def _plain(value):
    """numpy scalars are not JSON types; everything else is reported as text."""
    item = getattr(value, "item", None)
    return item() if callable(item) else str(value)


frame = pd.read_pickle({frame_path!r})
payload = falsification_program.falsify(frame)
sys.stdout.write({sentinel!r} + json.dumps(payload, default=_plain) + "\\n")
'''


class ExecutionResult(BaseModel):
    """The outcome of one attempt to run a falsification program.

    Guarantees: `ok` is True only when `payload` is present AND `failure_reason` is
    absent. The model refuses any other combination, so "succeeded with a reason it
    failed" cannot be constructed and then misread downstream.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    payload: dict[str, Any] | None = None
    failure_reason: str | None = None
    attempts: int = Field(default=1, ge=1, description="How many times execution was tried.")

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.ok and (self.payload is None or self.failure_reason is not None):
            raise ValueError("a successful result carries a payload and no failure reason")
        if not self.ok and (self.payload is not None or not self.failure_reason):
            raise ValueError("a failed result carries a reason and no payload")
        return self


def _failed(insight_id: str, reason: str, attempts: int = 1) -> ExecutionResult:
    """Build a failure and log it. Every exit from this module that is not a verified
    success comes through here, which is what makes the fail-closed claim auditable."""
    _log.warning(
        json.dumps(
            {"event": "execution_failed", "insight_id": insight_id, "reason": reason,
             "attempts": attempts}
        )
    )
    return ExecutionResult(ok=False, failure_reason=reason, attempts=attempts)


def _validate_payload(payload: object, nonce: str, config: VerificationConfig) -> str | None:
    """The reason `payload` is unusable, or None if it survives every check.

    The order is deliberate: structural problems are reported before the provenance
    check, so a malformed result is described as malformed rather than as a forgery;
    and the configuration match is checked last, so a forged stamp is reported as a
    forgery rather than as a wrong resample count.
    """
    if not isinstance(payload, dict):
        return (
            f"generated code returned {type(payload).__name__}, not a result mapping; "
            f"there is nothing to verify"
        )

    missing = sorted(REQUIRED_KEYS - set(payload))
    if missing:
        return (
            f"result is missing required keys {missing}; a partial result cannot become "
            f"a complete proof object (AGENTS.md 3.6)"
        )

    p_value = payload["p_value"]
    if not isinstance(p_value, (int, float)) or isinstance(p_value, bool):
        return f"p_value is {p_value!r}, which is not a number"
    if not 0.0 < float(p_value) <= 1.0:
        return (
            f"p_value is {p_value!r}, outside (0, 1]. A permutation p-value is add-one "
            f"floored at 1/(B+1), so an exact zero cannot come from the vetted test."
        )

    effect_size = payload["effect_size"]
    if (
        not isinstance(effect_size, (int, float))
        or isinstance(effect_size, bool)
        or not math.isfinite(effect_size)
    ):
        return (
            f"effect_size is {effect_size!r}, which is not a finite number. The gate compares "
            f"it against a floor, and every comparison against NaN is False -- a NaN effect "
            f"would pass the magnitude check it never took."
        )

    metric = payload["effect_metric"]
    if metric not in set(EffectMetric):
        return (
            f"effect_metric {metric!r} is not one of the vetted gating metrics "
            f"{sorted(m.value for m in EffectMetric)}; the gate has no band for it"
        )

    statistic = payload["statistic"]
    if effect_size != statistic:
        return (
            f"effect_size {effect_size!r} is not the stamped statistic {statistic!r}. The "
            f"gating effect IS the permutation statistic in every vetted test, and only the "
            f"statistic carries a provenance stamp -- an effect that differs from it is a "
            f"number the audited function did not produce."
        )

    fields = tuple(payload[name] for name in _STAMPED_FIELDS)
    if not provenance.verify(payload.get("provenance"), fields, nonce):
        return (
            "provenance check failed: the result carries no valid stamp for this run, so "
            "it did not come from pramana.verification.stats. Numbers that look right are "
            "not evidence -- only numbers the audited function produced are."
        )

    expected_n = config.statistics.n_permutations
    expected_seed = config.statistics.seed
    if payload["n_permutations"] != expected_n or payload["seed"] != expected_seed:
        return (
            f"the test ran with n_permutations={payload['n_permutations']!r}, "
            f"seed={payload['seed']!r}, but this run is configured for "
            f"n_permutations={expected_n}, seed={expected_seed}. A genuinely stamped result "
            f"from an under-powered or differently seeded test is still not the test this "
            f"run promised to reproduce (AGENTS.md 3.4)."
        )
    return None


def _run_once(
    program: FalsificationProgram, frame: pd.DataFrame, config: VerificationConfig
) -> tuple[dict[str, Any] | None, str | None, bool]:
    """One attempt. Returns `(payload, failure_reason, retryable)`.

    `retryable` distinguishes an execution failure (the machine misbehaved, trying
    again may help) from a validation failure (the code is what it is, and running it
    again produces the same answer more slowly).
    """
    nonce = provenance.new_nonce()
    with tempfile.TemporaryDirectory(prefix="pramana-exec-") as work_dir:
        work = Path(work_dir)
        (work / "falsification_program.py").write_text(program.source, encoding="utf-8")
        frame_path = work / "frame.pkl"
        frame.to_pickle(frame_path)
        harness_path = work / "harness.py"
        harness_path.write_text(
            _HARNESS.format(
                src_dir=str(Path(pramana.__file__).resolve().parents[1]),
                work_dir=str(work),
                frame_path=str(frame_path),
                sentinel=RESULT_SENTINEL,
            ),
            encoding="utf-8",
        )

        try:
            completed = subprocess.run(  # noqa: S603 -- source passed the import policy
                [sys.executable, str(harness_path)],
                capture_output=True,
                text=True,
                timeout=config.executor.timeout_seconds,
                env={
                    **{name: os.environ[name] for name in _PASSTHROUGH_ENV if name in os.environ},
                    provenance.NONCE_ENV_VAR: nonce,
                    "PYTHONHASHSEED": "0",
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
                cwd=work,
                **_resource_limits(config),
            )
        except subprocess.TimeoutExpired:
            return None, (
                f"execution exceeded the {config.executor.timeout_seconds}s timeout and was "
                f"killed; a test that does not finish has not falsified anything"
            ), True

        if completed.returncode != 0:
            detail = (completed.stderr or "").strip().splitlines()
            return None, (
                f"execution exited with status {completed.returncode}: "
                f"{detail[-1] if detail else 'no error output'}"
            ), True

        line = next(
            (
                raw[len(RESULT_SENTINEL) :]
                for raw in reversed((completed.stdout or "").splitlines())
                if raw.startswith(RESULT_SENTINEL)
            ),
            None,
        )
        if line is None:
            return None, "execution produced no result line; nothing was returned to verify", True

        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            return None, f"result is not valid JSON ({error.msg}); it cannot be trusted", False

        reason = _validate_payload(payload, nonce, config)
        return (None, reason, False) if reason else (payload, None, False)


def _resource_limits(config: VerificationConfig) -> dict[str, Any]:
    """The POSIX memory cap, or nothing on a platform that cannot apply one.

    See the module docstring: on Windows this returns `{}` and the cap is enforced by
    the container in deployment, not here.
    """
    try:
        import resource
    except ImportError:  # pragma: no cover -- Windows
        return {}

    limit = config.executor.max_memory_mb * 1024 * 1024

    def _apply() -> None:  # pragma: no cover -- runs in the forked child
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    return {"preexec_fn": _apply}


def execute(
    program: FalsificationProgram, frame: pd.DataFrame, config: VerificationConfig
) -> ExecutionResult:
    """Run one falsification program and return only a verified result, or a failure.

    Guarantees: `ok=True` implies the code passed the import policy, ran to completion
    inside the timeout, returned every required field, reported a p-value in (0, 1] and a
    finite effect size equal to the stamped statistic, named a vetted gating metric,
    carried a provenance stamp that verifies against a nonce generated for THIS
    execution, and ran with the configured resample count and seed. Any other outcome
    returns `ok=False` with a reason.
    There is no path in this function from a failure to a usable payload.
    """
    try:
        check_imports(program.source, config.executor.allowed_imports)
    except ImportPolicyViolation as violation:
        return _failed(program.insight_id, f"import policy violation: {violation}")

    attempts = 0
    reason = "execution was never attempted"
    for attempts in range(1, config.executor.max_retries + 2):
        payload, reason, retryable = _run_once(program, frame, config)
        if payload is not None:
            _log.info(
                json.dumps(
                    {"event": "execution_verified", "insight_id": program.insight_id,
                     "attempts": attempts, "p_value": payload["p_value"]}
                )
            )
            return ExecutionResult(ok=True, payload=payload, attempts=attempts)
        if not retryable:
            break

    return _failed(program.insight_id, reason or "execution failed", attempts=attempts)
