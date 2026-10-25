"""A rule-based chat assistant for servers without a model: it speaks the model's protocol.

It reads the question, picks tools by keyword and column name, and either answers from the
tool results or asks the gateway to test one claim, exactly as the model would. Everything
downstream is unchanged: the engine runs the tools, the wording guard checks every number,
the gateway decides any claim, and the ledger counts it. Selected explicitly by
`PRAMANA_CHAT_ENGINE=rules` (the offline profile's default), never as a fallback after a
model failure.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pramana.chat.guard import normalise
from pramana.common.llm_client import ChatMessage, Completion

_RELATION = re.compile(
    r"\b(?:associat\w*|relat\w*|correlat\w*|affect\w*|depend\w*|link\w*|differ\w*"
    r"|vary|varies|change\w* with|rise\w* with|increase\w* with|decrease\w* with"
    r"|higher|lower|versus|vs\.?|trend\w*|over time|impact\w*|influenc\w*|predict\w*)\b",
    re.IGNORECASE,
)
_MISSING = re.compile(r"\b(?:missing|null|blank|empty|nan|completeness)\b", re.IGNORECASE)
_BY = re.compile(r"\b(?:by|per|for each|across|in each|grouped by|split by)\b", re.IGNORECASE)
_STATS = (
    ("mean", re.compile(r"\b(?:average|mean|avg)\b", re.IGNORECASE)),
    ("median", re.compile(r"\bmedian\b", re.IGNORECASE)),
    ("min", re.compile(r"\b(?:min|minimum|lowest|smallest)\b", re.IGNORECASE)),
    ("max", re.compile(r"\b(?:max|maximum|highest|largest|biggest)\b", re.IGNORECASE)),
    ("std", re.compile(r"\b(?:std|spread|deviation|variability)\b", re.IGNORECASE)),
    ("n", re.compile(r"\b(?:how many|count|number of)\b", re.IGNORECASE)),
)
_LABELS = {
    "mean": "average",
    "median": "median",
    "min": "minimum",
    "max": "maximum",
    "std": "standard deviation",
    "n": "rows with a value",
}


def _fmt(value: Any) -> str:
    """A tool number as text the wording guard accepts: half-up, at most two decimals."""
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
        return f"{int(value):,}"
    places = Decimal("0.01") if abs(value) >= 1 else Decimal("0.0001")
    return str(Decimal(repr(float(value))).quantize(places, rounding=ROUND_HALF_UP))


def _words(name: str) -> str:
    return re.sub(r"[_\W]+", " ", normalise(name).lower()).strip()


def _named(question: str, columns: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Columns the question names (by name, or by name with spaces for underscores), in order."""
    text = " " + _words(question) + " "
    found = []
    for column in columns:
        for variant in {_words(column["name"]), _words(column.get("label") or "")}:
            if variant and (position := text.find(" " + variant + " ")) >= 0:
                found.append((position, column))
                break
    return [column for _, column in sorted(found, key=lambda item: item[0])]


class RuleChat:
    """One question's worth of rule-based replies. Holds state between turns."""

    def __init__(self) -> None:
        self.plan: list[dict[str, Any]] = []
        self.finish: Any = None
        self.results: list[tuple[str, dict[str, Any]]] = []
        self.started = False

    # ---- the protocol --------------------------------------------------------------
    def __call__(self, messages: Sequence[ChatMessage]) -> Completion:
        if not self.started:
            self.started = True
            self._start(messages)
        else:
            self._read(messages[-1].content)
        if self.plan:
            reply: dict[str, Any] = {"action": "tool", **self.plan.pop(0)}
        else:
            reply = self.finish(self) if callable(self.finish) else self._decline()
        return Completion(
            content=json.dumps(reply), returned_model="rules", input_tokens=0, output_tokens=0
        )

    def _read(self, content: str) -> None:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return
        if isinstance(payload, dict) and payload.get("ok") and payload.get("result_of"):
            self.results.append((payload["result_of"], payload.get("output") or {}))

    # ---- choosing what to do -------------------------------------------------------
    def _start(self, messages: Sequence[ChatMessage]) -> None:
        raw = messages[-1].content.split("\n", 1)[-1]
        data = json.loads(raw)
        question, columns = str(data.get("question", "")), list(data.get("columns", []))
        named = _named(question, columns)
        numeric = [c for c in named if c["role"] == "numeric"]
        grouping = [c for c in named if c["role"] in {"categorical", "ordinal"}]
        timed = [c for c in named if c.get("time_axis")]
        if _MISSING.search(question):
            self.plan = [{"tool": "missingness", "args": {}}]
            self.finish = RuleChat._answer_missing
        elif _RELATION.search(question) and len(named) >= 2:
            self._plan_test(named, numeric, grouping, timed)
        elif grouping and numeric and _BY.search(question):
            self.plan = [
                {
                    "tool": "compare_groups",
                    "args": {"value": numeric[0]["name"], "group": grouping[0]["name"]},
                }
            ]
            self.finish = RuleChat._answer_groups
        elif named:
            self.plan = [{"tool": "describe", "args": {"column": c["name"]}} for c in named[:3]]
            wanted = [key for key, pattern in _STATS if pattern.search(question)]
            self.finish = lambda chat: chat._answer_describe(wanted)
        else:
            self.plan = [{"tool": "missingness", "args": {}}]
            self.finish = RuleChat._answer_unmatched

    def _plan_test(
        self,
        named: list[dict[str, Any]],
        numeric: list[dict[str, Any]],
        grouping: list[dict[str, Any]],
        timed: list[dict[str, Any]],
    ) -> None:
        claim: dict[str, Any] | None = None
        if timed and numeric and timed[0] is not numeric[0]:
            claim = {"claim_type": "trend", "variables": [timed[0]["name"], numeric[0]["name"]]}
        elif grouping and numeric:
            claim = {
                "claim_type": "group_difference",
                "variables": [grouping[0]["name"], numeric[0]["name"]],
            }
        elif len(numeric) >= 2:
            claim = {
                "claim_type": "correlation",
                "variables": [numeric[0]["name"], numeric[1]["name"]],
            }
        if claim is None:
            self.plan = [{"tool": "describe", "args": {"column": c["name"]}} for c in named[:2]]
            self.finish = lambda chat: chat._answer_describe([])
            return
        self.plan = [{"tool": "describe", "args": {"column": v}} for v in claim["variables"]]
        if claim["claim_type"] == "group_difference":
            group, value = claim["variables"]
            self.plan.append({"tool": "compare_groups", "args": {"value": value, "group": group}})
        self.finish = lambda chat: chat._test(claim)

    # ---- finishing -----------------------------------------------------------------
    def _cites(self) -> list[str]:
        return [entry_id for entry_id, _ in self.results][:12]

    def _test(self, claim: dict[str, Any]) -> dict[str, Any]:
        claim = {**claim, "direction": None, "reference_group": None}
        if claim["claim_type"] == "group_difference":
            groups = next((out.get("groups") for _, out in self.results if out.get("groups")), None)
            if groups is not None and len(groups) == 2:
                first, second = groups
                if first.get("mean") is not None and second.get("mean") is not None:
                    claim["reference_group"] = first["group"]
                    # Direction is the reference group's, relative to the other one.
                    claim["direction"] = (
                        "positive" if first["mean"] >= second["mean"] else "negative"
                    )
            elif groups is not None and len(groups) < 2:
                return self._decline()
        elif claim["claim_type"] == "correlation":
            claim["direction"] = None
        return {"action": "test", "claim": claim}

    def _answer(self, text: str) -> dict[str, Any]:
        return {"action": "answer", "text": text, "cites": self._cites()}

    def _decline(self) -> dict[str, Any]:
        return self._answer(
            "I could not match this question to the table. Name a column, for example "
            "'average of <column>' or 'is <column> associated with <column>?'."
        )

    def _answer_describe(self, wanted: list[str]) -> dict[str, Any]:
        parts = []
        for _, out in self.results:
            name = out.get("column")
            if name is None:
                continue
            if "mean" in out:
                keys = wanted or ["mean", "median", "min", "max"]
                stats = [f"{_LABELS[k]} {_fmt(out[k])}" for k in keys if out.get(k) is not None]
                parts.append(f"{name}: " + ", ".join(stats) + f" (n = {_fmt(out['n'])}).")
            elif out.get("levels"):
                top = out["levels"][:5]
                shown = ", ".join(f"{level['label']} {_fmt(level['count'])}" for level in top)
                parts.append(f"{name}: most common values {shown} (n = {_fmt(out['n'])}).")
            else:
                parts.append(f"{name}: {_fmt(out['n'])} values present.")
        return self._answer(" ".join(parts)) if parts else self._decline()

    def _answer_groups(self) -> dict[str, Any]:
        out = next((o for _, o in self.results if o.get("groups")), None)
        if out is None:
            return self._decline()
        shown = "; ".join(
            f"{g['group']}: mean {_fmt(g['mean'])}, median {_fmt(g['median'])} (n = {_fmt(g['n'])})"
            for g in out["groups"]
            if g.get("mean") is not None and g.get("median") is not None
        )
        return self._answer(f"{out['value']} by {out['group']}: {shown}.")

    def _answer_missing(self) -> dict[str, Any]:
        out = next((o for _, o in self.results if "columns" in o), None)
        if out is None:
            return self._decline()
        gaps = [c for c in out["columns"] if c["missing"]]
        if not gaps:
            return self._answer(f"No usable column has missing values ({_fmt(out['rows'])} rows).")
        gaps.sort(key=lambda c: c["missing"], reverse=True)
        shown = ", ".join(
            f"{c['column']} {_fmt(c['missing'])} ({_fmt(c['missing_pct'])}%)" for c in gaps[:8]
        )
        return self._answer(f"Missing values out of {_fmt(out['rows'])} rows: {shown}.")

    def _answer_unmatched(self) -> dict[str, Any]:
        out = next((o for _, o in self.results if "columns" in o), None)
        names = ", ".join(c["column"] for c in (out or {}).get("columns", [])[:20])
        return self._answer(
            "I could not tell which column the question is about. Name a column from this list: "
            + names
            + "."
        )


__all__ = ["RuleChat"]
