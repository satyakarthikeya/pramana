"""Checks that decide whether the model's wording may be shown next to code-computed facts.

The model never computes a number. When it writes a sentence, code requires that every
number in it came from a tool result the sentence cites, and that it does not borrow the
vocabulary of a verdict or of causation. Anything that fails is withheld and replaced by the
tool results themselves. These checks are a net under the prompt, not a replacement for it:
a sentence can pass and still be badly worded, but it cannot carry a number nobody computed.

Text is normalised first (compatibility forms, minus signs, zero-width characters, look-alike
letters), because the model's output is untrusted and `signifi​cant` must not slip past.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

#: A number as a person writes it: sign, thousands commas, decimals (".75" too), optional %.
#: Digits glued to letters ("p0.001", "N999") are numbers too; column names are blanked first.
_NUMBER = re.compile(r"(?<![\d.])-?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)%?")

_NUMBER_WORDS = re.compile(
    r"\b(?:zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen"
    r"|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy"
    r"|eighty|ninety|hundred|thousand|million|billion|half|halves|third|thirds|quarter"
    r"|quarters|dozen|double|triple|twice|thrice)\b",
    re.IGNORECASE,
)

#: Words that belong to a verdict or to a causal claim. Verdicts come from the gate only.
_FORBIDDEN = re.compile(
    r"\b(?:significan\w*|statistical(?:ly)?|p[\s_.-]*val\w*|q[\s_.-]*val\w*|confidence"
    r"|verif\w*|reject\w*|confirm\w*|pass(?:es|ed)?|prov(?:e|es|ed|en|ing)|proof|caus\w+"
    r"|because|due to|lead(?:s|ing)? to|led to|result(?:s|ing|ed)? in|drives?|driven by"
    r"|driving|responsible for|impact(?:s|ed)? on|influenc\w*|determin\w*|reliabl\w*"
    r"|establish\w*|gateway|tested)\b|\b[pq]\s*[<=>≤≥]",
    re.IGNORECASE,
)

#: Stems checked again on the letters alone, so "sig-nificant" or "p val" cannot hide.
_STEMS = (
    "significan",
    "statistical",
    "pval",
    "qval",
    "verified",
    "confirmed",
    "rejected",
    "causal",
    "causation",
    "gateway",
    "proved",
)

_CONFUSABLES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i",
        "ѕ": "s", "ј": "j", "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H",
        "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X", "Α": "A", "Ε": "E", "Ο": "O",
        "ο": "o", "ν": "v", "ι": "i",
    }
)  # fmt: skip


def normalise(text: str) -> str:
    """Fold look-alike forms so the checks see what a reader sees."""
    folded = unicodedata.normalize("NFKC", text)
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")
    folded = folded.translate(_CONFUSABLES)
    for dash in "−–—‒‐‑":
        folded = folded.replace(dash, "-")
    return re.sub(r"\s+", " ", folded)


def forbidden_words(text: str) -> list[str]:
    """Verdict or causal vocabulary found in `text` (empty when the wording is acceptable)."""
    folded = normalise(text)
    found = {match.group(0).lower() for match in _FORBIDDEN.finditer(folded)}
    letters = re.sub(r"[^a-z]", "", folded.lower())
    found.update(stem for stem in _STEMS if stem in letters)
    return sorted(found)


def _numbers_in(value: Any, into: set[float]) -> None:
    """Collect every number a tool result contains, including numeric-looking labels."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int | float):
        if math.isfinite(float(value)):
            into.add(float(value))
    elif isinstance(value, str):
        for token in _NUMBER.findall(normalise(value)):
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
    """True when `shown` is `value` rounded half-up to the digits `shown` displays.

    A whole number is not accepted for a small fraction ("perfect 1" for 0.55): that would
    misstate the value rather than round it.
    """
    text = shown.rstrip("%").replace(",", "")
    places = len(text.split(".")[1]) if "." in text else 0
    try:
        wanted = Decimal(text)
        exact = Decimal(repr(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return False
    if wanted != exact:
        return False
    return not (places == 0 and abs(value) < 10 and value != int(value))


_UNIT_SQUARED = re.compile(r"(?<=[A-Za-z])[²³¹]")
_UNIT_EXPONENT = re.compile(r"(?<=/)([ckm]?m)[23]\b|\b([ckm]?m)[23]\b(?=[\s.,;)]|$)")


def _drop_unit_exponents(text: str) -> str:
    """Remove the exponent of an area or volume unit ("kg/m²", "kg/m2", "cm2").

    The exponent belongs to the unit, not to a statistic. It is dropped only straight after
    a metre-like unit or a superscript glued to a letter, so a stray digit is still checked.
    """
    text = _UNIT_SQUARED.sub("", text)
    return _UNIT_EXPONENT.sub(lambda m: m.group(1) or m.group(2), text)


def _blank_names(text: str, names: Iterable[str]) -> str:
    """Remove whole-token column names that contain a letter, so 'q1' is a name, not a number."""
    usable = sorted(
        {n for n in map(str, names) if len(n) >= 2 and any(c.isalpha() for c in n)},
        key=len,
        reverse=True,
    )
    if not usable:
        return text
    pattern = "|".join(re.escape(normalise(n)) for n in usable)
    return re.sub(rf"(?<![\w.])(?:{pattern})(?!\w)", " ", text)


def unsupported_numbers(
    text: str, outputs: Iterable[Any], *, names: Iterable[str] = ()
) -> list[str]:
    """Numbers (and number-like words) in `text` that no cited tool result contains.

    Only what the cited tool results hold counts as supported; the user's own question does
    not, otherwise a false premise ("is the mean 999?") would be echoed back as fact. A
    percentage may be the stored value or a stored fraction (at most 1 in size) times one
    hundred; no other arithmetic is accepted. Spelled-out numbers and fraction glyphs are
    reported too, because they cannot be matched, so the model is told to use digits.
    """
    supported: set[float] = set()
    for output in outputs:
        _numbers_in(output, supported)
    text = _drop_unit_exponents(text)
    problems = [
        ch
        for ch in text
        if ch.isnumeric() and not ch.isdecimal() and unicodedata.numeric(ch, None) is not None
    ]
    cleaned = _blank_names(normalise(text), names)
    problems += [m.group(0).lower() for m in _NUMBER_WORDS.finditer(cleaned)]
    for token in _NUMBER.findall(cleaned):
        percent = token.endswith("%")
        if any(
            _matches(token, v) or (percent and abs(v) <= 1 and _matches(token, round(v * 100, 10)))
            for v in supported
        ):
            continue
        problems.append(token)
    return problems
