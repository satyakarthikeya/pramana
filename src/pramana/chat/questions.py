"""Conservative question interpretation; never computes evidence or chooses a verdict."""

from __future__ import annotations

import re

from pramana.analysis.reader import DataBrief
from pramana.analysis.sectors import load_packs, roles_for

_ALIASES = {
    "systolic_bp": {"systolic blood pressure", "systolic pressure", "blood pressure", "sbp"},
    "diastolic_bp": {"diastolic blood pressure", "diastolic pressure", "blood pressure", "dbp"},
    "glucose": {"blood sugar", "blood glucose"},
    "bmi": {"body mass index"},
}

# Lexical units only: these select a column, never convert data or infer a statistic.
_UNITS = {
    "c": ("celsius",), "f": ("fahrenheit",), "usd": ("usd", "dollars"),
    "rpm": ("rpm", "revolutions per minute"), "pct": ("percent", "percentage"),
    "percent": ("percent",), "kg": ("kilograms",), "cm": ("centimeters",),
    "mmHg": ("mmhg",), "mgdl": ("mgdl",), "years": ("years",),
    "year": ("years",), "yrs": ("years",), "yr": ("years",),
    "days": ("days",), "ms": ("milliseconds",), "kPa": ("kilopascals",),
    "MPa": ("megapascals",),
    "V": ("volts",), "A": ("amps", "amperes"), "mA": ("milliamps", "milliamperes"),
    "W": ("watts",), "kW": ("kilowatts",),
    "Wh": ("watt hours",), "kWh": ("kilowatt hours",),
}


def _words(text: str) -> str:
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return " ".join(re.findall(r"[^\W_]+", text.casefold()))


def resolve_columns(
    question: str, allowed: set[str], brief: DataBrief | None,
) -> tuple[set[str], set[str]]:
    """Resolve whole names/known meanings; ambiguous references never become matches.

    More specific phrases win over overlapping shorter phrases. A shared word in a
    label is not sufficient, and looking at a column cannot settle a user's ambiguity.
    """
    aliases = {name: {_words(name)} for name in allowed}
    for name in allowed:
        without_brackets = _words(re.sub(r"\([^)]*\)|\[[^]]*\]", " ", name))
        aliases[name].add(without_brackets)
        canonical = _words(name)
        for symbol, labels in _UNITS.items():
            # Match both conventional symbols (kWh -> k wh) and lowercase headers.
            for unit in {_words(symbol), _words(symbol.casefold())}:
                if canonical.endswith(" " + unit):
                    base = canonical[:-len(unit)].strip()
                    aliases[name].add(base)
                    for label in labels:
                        aliases[name].update({base + " " + label, base + " in " + label})
    if brief:
        for column in brief.columns:
            if column.name in aliases and column.label:
                aliases[column.name].add(_words(column.label))
    for pack in load_packs().values():
        for name, role in roles_for(sorted(allowed), pack).items():
            if role != "entity":
                aliases[name].add(_words(role))
                aliases[name].update(_ALIASES.get(role, set()))
    query = " " + _words(question) + " "
    spans: dict[tuple[int, int], set[str]] = {}
    for name, phrases in aliases.items():
        for phrase in phrases:
            if phrase:
                for match in re.finditer(r"(?<= )" + re.escape(phrase) + r"(?= )", query):
                    spans.setdefault(match.span(), set()).add(name)
    named: set[str] = set()
    ambiguous: set[str] = set()
    for (start, end), columns in spans.items():
        if any(left <= start and right >= end and right - left > end - start
               for left, right in spans):
            continue
        if len(columns) == 1:
            named.update(columns)
        else:
            ambiguous.update(columns)
    # An explicit, separately named column resolves its own ambiguous alias.
    return named, ambiguous - named


def question_limits(question: str) -> list[str]:
    """Return code-written limits for the unsupported parts of a question."""
    notes = []
    if re.search(r"\b(?:caus\w*|affect\w*|impact\w*)\b|\beffect of\b", question, re.I):
        notes.append(
            "Causation: this table alone cannot establish whether changing one variable "
            "changes another. Any association test here addresses association only."
        )
    if re.search(
        r"\b(?:representative|representativeness|generali[sz]\w*)\b|"
        r"\b(?:general|whole|wider|entire) population\b", question, re.I,
    ):
        notes.append(
            "Population representativeness: this table alone cannot establish that its "
            "records represent the general population. Sampling documentation, the target "
            "population and any survey weights are needed to assess that."
        )
    return notes


def asks_for_forecast(question: str) -> bool:
    """Recognise prediction requests in either word order, leaving recorded metrics usable.

    This identifies an unavailable capability, never predicts a value. Historical forecast
    error/accuracy columns still belong to the descriptive tools.
    """
    text = _words(question)
    forecast = re.search(
        r"\bforecast(?:s|ing)?\b(?!\s+(?:errors?|accuracy|residuals?|bias|performance)\b)", text,
    )
    prediction = re.search(r"\bpredict(?:s|ed|ing|ion|ions)?\b", text)
    horizon = re.search(r"\b(?:next|future|tomorrow|upcoming|later)\b|\b\d{4}\b", text)
    will = re.search(r"\bwill\b", text)
    return bool(forecast or (horizon and (prediction or will)))
