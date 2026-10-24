"""The refuter: a model that suggests EXTRA places to look for a flaw (design v3, S8).

Models propose; code decides. The refuter sees the claim's type and variable names and the
table's column NAMES and kinds (numeric or categorical, number of levels), never a value.
It may suggest up to a few columns to hold fixed (A3) and to look inside (A4). Code
validates every name against the table; anything unknown, a claim's own variable, or past
the configured cap is dropped. A suggestion is ADDED to the checks the code already runs
and can never replace or remove one, so the refuter can only make a claim harder to pass.
It never writes a number, a verdict or a sentence the user reads, and a failure of any
kind (no key, no tracing, bad output) yields no suggestions and the full default checks.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from pramana.verification.attacks import AttackHints, ClaimView
from pramana.verification.config import VerificationConfig
from pramana.verification.schemes import PERIOD_COLUMN

_SYSTEM = (
    "You help find weaknesses in a statistical claim about a table. You are shown the "
    "claim's type and variable names and the table's column names with their kinds. You "
    "never see data values and you never judge whether the claim is true.\n"
    "Suggest columns a careful analyst would check:\n"
    '- "controls": numeric columns that might drive BOTH variables (a third variable);\n'
    '- "groups": categorical columns inside which the relationship should be re-checked '
    "(for example a region or product).\n"
    'Reply with JSON only: {"controls": [names], "groups": [names]}. Use names exactly as '
    "listed, at most 2 in each list, and nothing else."
)

#: How a model call is made: (system prompt, user prompt, config) -> text. Replaced in tests.
CallModel = Callable[[str, str, VerificationConfig], str]


@dataclass(frozen=True)
class RefuterOutcome:
    """The hints that survived validation, and why the rest did not."""

    hints: AttackHints
    status: str  # "used" | "no_suggestions" | "unavailable"
    dropped: tuple[str, ...] = ()


def column_profile(claim: ClaimView, rows: pd.DataFrame, max_levels: int) -> list[dict[str, object]]:
    """Names and kinds only: never a value, never a count of rows."""
    out: list[dict[str, object]] = []
    for name in rows.columns:
        if name in (PERIOD_COLUMN, claim.var_x, claim.var_y):
            continue
        numeric = pd.api.types.is_numeric_dtype(rows[name])
        levels = int(rows[name].dropna().nunique())
        out.append(
            {
                "name": str(name),
                "kind": "numeric" if numeric else "categorical",
                "levels": levels if levels <= max_levels else f"more than {max_levels}",
            }
        )
    return out


def _call_default(system: str, user: str, config: VerificationConfig) -> str:
    from pramana.verification.falsification.generator import call_model

    return call_model(system, user, config)


def suggest_hints(
    claim: ClaimView,
    rows: pd.DataFrame,
    config: VerificationConfig,
    *,
    call: CallModel | None = None,
) -> RefuterOutcome:
    """Validated hints for the attacks. Never raises; a failure is `unavailable` with no hints."""
    attacks = config.attacks
    profile = column_profile(claim, rows, attacks.max_subgroup_levels)
    if not profile:
        return RefuterOutcome(AttackHints(), "no_suggestions")
    user = json.dumps(
        {
            "claim_type": claim.claim_type.value,
            "variables": [claim.var_x, claim.var_y],
            "columns": profile,
        }
    )
    try:
        text = (call or _call_default)(_SYSTEM, user, config)
        match = re.search(r"\{.*\}", text, re.S)
        payload = json.loads(match.group(0)) if match else {}
        if not isinstance(payload, dict):
            raise ValueError("not an object")
    except Exception:  # no key, no tracing, bad output: no suggestions, never a verdict change
        return RefuterOutcome(AttackHints(), "unavailable")

    known = {str(c["name"]): c for c in profile}
    dropped: list[str] = []

    def pick(key: str, kind: str, cap: int) -> tuple[str, ...]:
        names = payload.get(key, [])
        chosen: list[str] = []
        for name in names if isinstance(names, list) else []:
            if not isinstance(name, str) or name not in known:
                dropped.append(f"{key}: {str(name)[:40]!r} is not a column")
            elif key == "controls" and known[name]["kind"] != kind:
                dropped.append(f"{key}: {name!r} is not numeric")
            elif key == "groups" and not isinstance(known[name]["levels"], int):
                dropped.append(f"{key}: {name!r} has too many levels to group by")
            elif name in chosen:
                continue
            elif len(chosen) >= cap:
                dropped.append(f"{key}: {name!r} is past the limit of {cap}")
            else:
                chosen.append(name)
        return tuple(chosen)

    hints = AttackHints(
        controls=pick("controls", "numeric", attacks.refuter_max_controls),
        groups=pick("groups", "categorical", attacks.refuter_max_groups),
    )
    status = "used" if hints.controls or hints.groups else "no_suggestions"
    return RefuterOutcome(hints, status, tuple(dropped))
