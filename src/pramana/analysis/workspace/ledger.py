"""A record of everything the analyst looked at, so no exploration goes uncounted.

Why this exists: if a scan examines 200 pairs and proposes the best eight, the
multiple-testing correction over those eight does not account for the other 192. The
ledger keeps the count and the trail, so the results can say plainly what was screened
and a reviewer can replay every step. It records; it never decides anything.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_SUMMARY_CHARS = 300
MAX_ENTRIES = 200
MAX_SHOWN_ENTRIES = 60


class LedgerEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_id: str
    kind: Literal["tool", "python"]
    name: str
    args: dict[str, Any]
    ok: bool
    summary: str
    #: Hypotheses this step examined. Tools report an exact number; a free-form Python
    #: run cannot be audited for it, so it counts as zero and is reported separately.
    examined: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class ExplorationSummary(BaseModel):
    """What the analyst looked at, kept next to the results so nothing is hidden.

    `examined` is how many hypotheses (column pairs) were looked at; `proposed` is how many
    were handed to the gateway; `tested` is how many the gateway actually tested. The
    multiple-testing correction covers `tested` only.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    engine: Literal["scan", "agent", "api"]
    examined: int = Field(ge=0)
    proposed: int = Field(default=0, ge=0)
    tested: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    python_runs: int = Field(default=0, ge=0)
    turns: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    entries: list[LedgerEntry] = Field(default_factory=list, max_length=MAX_SHOWN_ENTRIES)


class ExplorationLedger:
    """Append-only log of tool and Python steps. Totals stay exact even past the entry cap."""

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._counter = 0
        self.examined = 0
        self.python_runs = 0
        self.tool_calls = 0

    @property
    def entries(self) -> list[LedgerEntry]:
        return list(self._entries)

    def next_id(self) -> str:
        self._counter += 1
        return f"x{self._counter}"

    def add(
        self,
        entry_id: str,
        *,
        kind: Literal["tool", "python"],
        name: str,
        args: dict[str, Any],
        ok: bool,
        output: Any,
        examined: int,
        duration_ms: int,
    ) -> LedgerEntry:
        text = output if isinstance(output, str) else json.dumps(output, default=str)
        entry = LedgerEntry(
            entry_id=entry_id,
            kind=kind,
            name=name,
            args=json.loads(json.dumps(args, default=str)),
            ok=ok,
            summary=text[:MAX_SUMMARY_CHARS],
            examined=examined,
            duration_ms=duration_ms,
        )
        self.examined += examined
        if kind == "python":
            self.python_runs += 1
        else:
            self.tool_calls += 1
        if len(self._entries) < MAX_ENTRIES:
            self._entries.append(entry)
        return entry
