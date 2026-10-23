"""Checks that decide whether the model's wording may be shown next to code-computed facts.

The model never computes a number. When it writes a sentence, code requires that every
number in it came from a tool result the sentence cites (or from the user's own question),
and that it does not borrow the vocabulary of a verdict or of causation. Anything that
fails is withheld and replaced by the tool results themselves. These checks are a net
under the prompt, not a replacement for it: a sentence can pass and still be badly
worded, but it cannot carry a number nobody computed.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

#: A number as a person writes it: optional sign, thousands commas, decimals, optional %.
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?%?")

#: Words that belong to a verdict or to a causal claim. Verdicts come from the gate only.
_FORBIDDEN = re.compile(
    r"\b(?:significan\w*|statistical(?:ly)?|p[- ]?values?|q[- ]?values?"
    r"|confidence|verified|rejected|pass(?:es|ed)?|proves?|proven|causes?|caused|causing"
    r"|because of|due to|leads? to|led to|results? in|drives?|driven by|responsible for"
    r"|impact on)\b|\b[pq]\s*[<=>≤≥]",
    re.IGNORECASE,
)


def forbidden_words(text: str) -> list[str]:
    """Verdict or causal vocabulary found in `text` (empty when the wording is acceptable)."""
    return sorted({match.group(0).lower() for match in _FORBIDDEN.finditer(text)})


def _numbers_in(value: Any, into: set[float]) -> None:
    """Collect every number a tool result contains, including numeric-looking labels."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int | float):
        if math.isfinite(float(value)):
            into.add(float(value))
    elif isinstance(value, str):
        for token in _NUMBER.findall(value):
            parsed = _parse(token)
            if parsed is not None:
                into.add(parsed)
    elif isinstance(value, dict):
        for key, item in value.items():
            _numbers_in(key, into)
            _numbers_in(item, into)
    elif isinstance(value, list | tuple):
        into.add(float(len(value)))  # "there are 3 groups" is a count of what was returned
        for item in value:
            _numbers_in(item, into)


def _parse(token: str) -> float | None:
    try:
        return float(token.rstrip("%").replace(",", ""))
    except ValueError:
        return None


def _matches(shown: str, value: float) -> bool:
    """True when `shown` is `value` rounded half-up to the digits `shown` displays."""
    text = shown.rstrip("%").replace(",", "")
    places = len(text.split(".")[1]) if "." in text else 0
    try:
        wanted = Decimal(text)
        exact = Decimal(repr(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return False
    return wanted == exact


def unsupported_numbers(
    text: str, outputs: Iterable[Any], *, question: str = "", names: Iterable[str] = ()
) -> list[str]:
    """Numbers in `text` that no cited tool result (or the question) contains.

    Column names and group labels may hold digits ("q1", "2019"), so the names given are
    blanked out of the sentence first. A percentage may be the stored value or the stored
    fraction times one hundred; no other arithmetic is accepted.
    """
    supported: set[float] = set()
    for output in outputs:
        _numbers_in(output, supported)
    _numbers_in(question, supported)
    cleaned = text
    for name in sorted({str(n) for n in names}, key=len, reverse=True):
        if name:
            cleaned = cleaned.replace(name, " ")
    missing = []
    for token in _NUMBER.findall(cleaned):
        percent = token.endswith("%")
        if any(_matches(token, v) or (percent and _matches(token, v * 100)) for v in supported):
            continue
        missing.append(token)
    return missing
