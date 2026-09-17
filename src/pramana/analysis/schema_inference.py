"""Column type/semantic classification (numeric, categorical, ordinal, datetime, ID-like).

Deterministic heuristics first; Gemma (local) only for ambiguous columns.

What this produces and why it is shaped this way
------------------------------------------------
A `SchemaProfile`: one `ColumnProfile` per column, carrying the role, the confidence
the heuristics had in it, and the reasons that produced it. The reasons are not
decoration. When a column ends up `UNKNOWN`, the next thing that happens is a human
or the semantic refiner looking at it, and "0.82 distinct values per row, dtype
object" is actionable where "unclassified" is not.

Fail-closed, and what that means here
--------------------------------------
There is no "best guess" role. A column the heuristics cannot place at or above
`min_confidence`, or that has fewer than `min_non_null` usable values, is `UNKNOWN`
with `usable_for_hypotheses=False`. Candidate generation reads that flag and skips
the column entirely.

The cost of the other choice is concrete. A free-text notes column guessed
`CATEGORICAL` becomes a grouping variable with 400 levels; a record number guessed
`NUMERIC` becomes a correlation candidate that is really a claim about row order.
Both produce a syntactically valid `CandidateInsight` that consumes a slot in the
run's BH family and dilutes every real claim's q-value. Refusing to classify costs
one missed hypothesis; guessing costs the gateway's correction.

No role is decided by a column's NAME alone. Values decide; a name from the
vocabulary constants below can only corroborate a decision the values already
support, and the two places it is consulted (identifier, time axis) both need the
value statistics to agree first. The demo datasets name columns `RIDAGEYR` and
`v024`; a classifier keyed on names would work on neither.

The identifier rule is the one that cuts both ways, so it is worth stating: a column
where every value is distinct is called an identifier only if its name says so.
Without that it stays `UNKNOWN` -- free text and an unnamed key are indistinguishable
from the values, both are excluded from hypotheses either way, and `UNKNOWN` is the
one that reaches the semantic refiner.

Gemma's place in this
----------------------
`SemanticRefiner` is the seam. Heuristics run first and always; the refiner is offered
only the columns they left `UNKNOWN`, which is what `use_llm_for_ambiguous_only`
means. No refiner is wired in here -- there is no Gemma client in the repository yet
-- so the default is no refinement, and ambiguous columns stay `UNKNOWN`. That is the
fail-closed default, not a stub standing in for one.

Owner: P. Rohith (built by P.P. Satya Karthikeya -- team-agreed cross-module work)
Scope: scope/SCOPE_P_Rohith.md 2, component 2 / 4, step 2
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from pramana.analysis.config import SchemaInferenceConfig

#: Name fragments that corroborate an identifier. Vocabulary, not a threshold, so it
#: lives in code: widening it changes what the module is willing to call an ID, which
#: is a design decision for review rather than a YAML edit (the same line
#: `verification/admissibility.py` draws for its claim vocabulary).
ID_NAME_TOKENS: frozenset[str] = frozenset(
    {"id", "identifier", "index", "key", "uuid", "guid", "seqn", "serial", "code", "no"}
)

#: Name fragments that mark an ordered column as a time axis, which is what separates
#: a trend candidate from a plain correlation. `month` as an integer 1-12 is ordinal
#: either way; only the name says it advances.
TIME_NAME_TOKENS: frozenset[str] = frozenset(
    {
        "date",
        "time",
        "year",
        "yr",
        "month",
        "mon",
        "week",
        "day",
        "quarter",
        "period",
        "wave",
        "round",
        "timestamp",
        "epoch",
    }
)

#: Confidence assigned when a decision rests on the pandas dtype alone. A datetime64
#: column is datetime; there is nothing to be uncertain about.
_CERTAIN = 1.0

#: Confidence for a decision resting on value statistics that could plausibly have
#: come out the other way -- a 12-level integer that might be a count, say.
_LIKELY = 0.8

#: Confidence for a decision that only just cleared its heuristic. Sits below the
#: shipped `min_confidence`, so it lands in the refiner's queue rather than in a
#: hypothesis.
_WEAK = 0.5


class ColumnRole(StrEnum):
    """What a column IS, for the purpose of proposing hypotheses about it.

    Deliberately NOT in `pramana.contracts`: this vocabulary is the analysis module's
    internal view of a dataframe, it does not cross the gateway boundary, and the
    contracts package is frozen and shared. If orchestration ever needs to speak it,
    that is the moment to promote it -- announced, per `OWNERSHIP.md`, not assumed.

    `UNKNOWN` is a real answer, not a missing one. It is what the heuristics say when
    they are not confident enough to be believed, and it is what keeps a guessed role
    out of the gateway's hypothesis family.
    """

    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    ORDINAL = "ordinal"
    DATETIME = "datetime"
    ID_LIKE = "id_like"
    UNKNOWN = "unknown"


#: Roles a hypothesis strategy can actually build a claim from. `ID_LIKE` is excluded
#: because a correlation with a record number is a claim about row order, and
#: `UNKNOWN` because that is the whole point of it.
USABLE_ROLES: frozenset[ColumnRole] = frozenset(
    {ColumnRole.NUMERIC, ColumnRole.CATEGORICAL, ColumnRole.ORDINAL, ColumnRole.DATETIME}
)


class ColumnProfile(BaseModel):
    """One column's inferred role, with the evidence that produced it.

    Guarantees: `usable_for_hypotheses` is True only when the role is in
    `USABLE_ROLES` AND `confidence >= min_confidence` AND the column cleared
    `min_non_null` -- so a consumer that honours this one flag cannot accidentally
    build a claim on a guess. `reasons` is never empty.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    role: ColumnRole
    dtype: str = Field(min_length=1, description="The pandas dtype the decision saw.")
    confidence: float = Field(ge=0.0, le=1.0, description="How much the heuristics back the role.")
    n_non_null: int = Field(ge=0)
    n_unique: int = Field(ge=0, description="Distinct non-null values.")
    unique_ratio: float = Field(
        ge=0.0, le=1.0, description="Distinct non-null values per non-null row."
    )
    missing_ratio: float = Field(ge=0.0, le=1.0)
    is_time_like: bool = Field(
        default=False,
        description="Datetime, or an ordered column whose name marks it as a time axis. "
        "Trend candidates need one of these on the x side.",
    )
    levels: list[str] = Field(
        default_factory=list,
        description="Distinct values, for a categorical or ordinal column only. Empty "
        "otherwise -- a numeric column's values are not a vocabulary.",
    )
    usable_for_hypotheses: bool = Field(
        description="Whether candidate generation may build a claim on this column."
    )
    reasons: list[str] = Field(
        min_length=1, description="Why this role, in the order the checks fired."
    )


class SchemaProfile(BaseModel):
    """Every column's role for one dataframe.

    Guarantees: `columns` has exactly one entry per column of the frame it was
    inferred from, keyed by column name and in the frame's own column order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_rows: int = Field(ge=0)
    n_columns: int = Field(ge=0)
    columns: dict[str, ColumnProfile]

    def role_of(self, column: str) -> ColumnRole:
        """The inferred role of `column`. `UNKNOWN` for a column that is not here."""
        profile = self.columns.get(column)
        return ColumnRole.UNKNOWN if profile is None else profile.role

    def usable(self, *roles: ColumnRole) -> list[str]:
        """Usable column names carrying any of `roles`, in the frame's column order.

        Guarantees: every name returned belongs to a column that passed the
        confidence and non-null floors, so a strategy never has to re-check.
        """
        wanted = set(roles) or set(USABLE_ROLES)
        return [
            name
            for name, profile in self.columns.items()
            if profile.usable_for_hypotheses and profile.role in wanted
        ]

    @property
    def ambiguous(self) -> list[str]:
        """Columns the heuristics refused to classify -- the semantic refiner's queue."""
        return [
            name for name, profile in self.columns.items() if profile.role is ColumnRole.UNKNOWN
        ]


class SemanticRefiner(Protocol):
    """The Gemma seam (`AGENTS.md` 2): cheap semantic help for ambiguous columns only.

    An implementation receives the heuristics' draft profile -- role `UNKNOWN`, with
    the value statistics and the reasons that got it there -- and returns a role it is
    confident in, or `None` to leave the column unclassified.

    Returning `None` must stay a first-class answer. A refiner that always produces
    something is a guess generator, and the column it guessed about becomes a claim
    the gateway spends a correction slot on.
    """

    def refine(self, profile: ColumnProfile) -> ColumnRole | None:
        """The role for `profile`'s column, or `None` to leave it `UNKNOWN`."""
        ...


#: Separators and case changes that split a column name into words. The second
#: alternative catches camelCase (`PatientID` -> `Patient`, `ID`), the third splits a
#: digit run off a word (`v024` -> `v`, `024`).
_WORD_BOUNDARY = re.compile(
    r"[_\-. /]+|(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])"
)


def _name_matches(column: str, vocabulary: frozenset[str]) -> bool:
    """Whether `column`'s name contains a token from `vocabulary` as a whole word.

    Whole words only, so `patient_id` and `PatientID` both hit `id` while `video` and
    `avoidance` do not. A substring match here would be worse than no name hint at
    all: it would silently reclassify columns on a coincidence of spelling.
    """
    tokens = {part.casefold() for part in _WORD_BOUNDARY.split(str(column)) if part}
    return bool(tokens & vocabulary)


#: What `pd.api.types.infer_dtype` calls values that are actually numbers. Checked on
#: the VALUES rather than the column dtype, because an object column holding floats
#: reports dtype `object` and would otherwise be handled as text.
_NUMERIC_VALUE_KINDS: frozenset[str] = frozenset(
    {"integer", "floating", "mixed-integer-float", "decimal", "boolean"}
)

#: Value kinds a datetime parse may be attempted on. Deliberately narrow: `4.0` and
#: `2011` both parse as nanosecond epochs, so offering numbers to the parser turns
#: any numeric column into a spurious timestamp -- the exact fail-open this module
#: exists to avoid.
_TEXTUAL_VALUE_KINDS: frozenset[str] = frozenset({"string", "unicode", "date", "datetime"})


def _value_kind(series: pd.Series) -> str:
    """What `series` actually HOLDS, as opposed to what its dtype says."""
    return str(pd.api.types.infer_dtype(series, skipna=True))


def _parseable_as_datetime(series: pd.Series) -> float:
    """Share of non-null values that parse as timestamps, in `[0, 1]`.

    Returns 0.0 unless the values are textual. Years like 2011 parse happily as
    nanosecond epochs, and calling an integer year a datetime would hand the trend
    strategy a column it would then convert straight back to a number.
    """
    non_null = series.dropna()
    if non_null.empty or _value_kind(non_null) not in _TEXTUAL_VALUE_KINDS:
        return 0.0
    parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
    return float(parsed.notna().sum()) / float(len(non_null))


def _classify_numeric(
    series: pd.Series, name: str, n_unique: int, config: SchemaInferenceConfig
) -> tuple[ColumnRole, float, list[str]]:
    """Role for a numeric-dtype column: ordinal, identifier-like, or numeric."""
    reasons = [f"dtype {series.dtype} is numeric"]

    if pd.api.types.is_bool_dtype(series):
        return ColumnRole.CATEGORICAL, _CERTAIN, [*reasons, "boolean dtype: two fixed levels"]

    non_null = series.dropna()
    integral = bool(non_null.empty) or bool((non_null % 1 == 0).all())

    # An integer column with as many distinct values as rows, whose name says so, is a
    # record number. The name is required: a genuinely continuous measurement also has
    # a distinct value per row, and calling THAT an identifier would throw away the
    # most informative column in the frame.
    if integral and _name_matches(name, ID_NAME_TOKENS):
        unique_ratio = float(n_unique) / float(max(len(non_null), 1))
        if unique_ratio >= config.id_unique_ratio:
            return (
                ColumnRole.ID_LIKE,
                _CERTAIN,
                [*reasons, f"integral, name reads as an identifier, {unique_ratio:.2f} distinct"],
            )

    if integral and 2 <= n_unique <= config.ordinal_max_levels:
        return (
            ColumnRole.ORDINAL,
            _LIKELY,
            [*reasons, f"integral with {n_unique} levels (<= {config.ordinal_max_levels})"],
        )

    return ColumnRole.NUMERIC, _CERTAIN, [*reasons, f"{n_unique} distinct values, continuous"]


def _classify_labelled(
    series: pd.Series,
    name: str,
    n_unique: int,
    unique_ratio: float,
    config: SchemaInferenceConfig,
) -> tuple[ColumnRole, float, list[str]]:
    """Role for a non-numeric, non-datetime column: identifier, categorical, or unknown."""
    reasons = [f"dtype {series.dtype} is not numeric"]

    if unique_ratio >= config.id_unique_ratio:
        # Uniqueness alone does not make an identifier -- a free-text notes column is
        # equally unique. The name has to corroborate it. Without that the column is
        # UNKNOWN, which is the same exclusion from hypotheses reached honestly, and
        # it lands in the semantic refiner's queue where a guessed ID would not.
        if _name_matches(name, ID_NAME_TOKENS):
            return (
                ColumnRole.ID_LIKE,
                _CERTAIN,
                [
                    *reasons,
                    f"{unique_ratio:.2f} distinct values per row "
                    f"(>= {config.id_unique_ratio}) and the name reads as an identifier",
                ],
            )
        return (
            ColumnRole.UNKNOWN,
            _WEAK,
            [
                *reasons,
                f"{unique_ratio:.2f} distinct values per row "
                f"(>= {config.id_unique_ratio}) but nothing names it an identifier; "
                f"free text and an unnamed key look identical from here",
            ],
        )

    if 2 <= n_unique <= config.categorical_max_levels:
        return (
            ColumnRole.CATEGORICAL,
            _CERTAIN,
            [*reasons, f"{n_unique} levels (<= {config.categorical_max_levels})"],
        )

    # Too many levels to group by, not unique enough to be an identifier. Free text,
    # most likely. Guessing either way produces a claim nobody can read.
    return (
        ColumnRole.UNKNOWN,
        _WEAK,
        [
            *reasons,
            f"{n_unique} levels exceeds categorical_max_levels "
            f"({config.categorical_max_levels}) but is not identifier-unique",
        ],
    )


def infer_column(
    series: pd.Series, name: str, config: SchemaInferenceConfig
) -> ColumnProfile:
    """Classify one column from its values, with its name as a corroborating hint only.

    Guarantees: deterministic for a given `(series, config)` -- no sampling, no model
    call, no dependence on the other columns. Never raises for an empty, all-null or
    single-valued column; those come back `UNKNOWN` and unusable.
    """
    n_rows = int(len(series))
    non_null = series.dropna()
    n_non_null = int(len(non_null))
    n_unique = int(non_null.nunique())
    unique_ratio = float(n_unique) / float(n_non_null) if n_non_null else 0.0
    missing_ratio = float(n_rows - n_non_null) / float(n_rows) if n_rows else 0.0
    dtype = str(series.dtype)

    if n_non_null < config.min_non_null:
        return ColumnProfile(
            name=name,
            role=ColumnRole.UNKNOWN,
            dtype=dtype,
            confidence=0.0,
            n_non_null=n_non_null,
            n_unique=n_unique,
            unique_ratio=unique_ratio,
            missing_ratio=missing_ratio,
            usable_for_hypotheses=False,
            reasons=[
                f"{n_non_null} non-null values is below min_non_null "
                f"({config.min_non_null}); nothing can be inferred responsibly"
            ],
        )

    if n_unique < 2:
        # One value (or none) supports no claim of any shape: every association with a
        # constant is exactly zero. Caught before the role branches so no branch has
        # to rediscover it, and so a constant object column cannot slip into the
        # datetime parser on its way past.
        return ColumnProfile(
            name=name,
            role=ColumnRole.UNKNOWN,
            dtype=dtype,
            confidence=0.0,
            n_non_null=n_non_null,
            n_unique=n_unique,
            unique_ratio=unique_ratio,
            missing_ratio=missing_ratio,
            usable_for_hypotheses=False,
            reasons=[f"{n_unique} distinct values; a constant column supports no claim"],
        )

    if pd.api.types.is_datetime64_any_dtype(series):
        role, confidence, reasons = (
            ColumnRole.DATETIME,
            _CERTAIN,
            [f"dtype {dtype} is a datetime"],
        )
    elif pd.api.types.is_numeric_dtype(series) or _value_kind(non_null) in _NUMERIC_VALUE_KINDS:
        # The second test catches an object column that holds numbers -- cleaning
        # normally converts those, but this module must not depend on having been
        # handed a cleaned frame to avoid calling a float column text.
        series = pd.to_numeric(series, errors="coerce")
        role, confidence, reasons = _classify_numeric(series, name, n_unique, config)
    else:
        parse_ratio = _parseable_as_datetime(series)
        if parse_ratio >= config.datetime_parse_min_ratio:
            role, confidence, reasons = (
                ColumnRole.DATETIME,
                _LIKELY,
                [
                    f"{parse_ratio:.2f} of non-null values parse as timestamps "
                    f"(>= {config.datetime_parse_min_ratio})"
                ],
            )
        else:
            role, confidence, reasons = _classify_labelled(
                series, name, n_unique, unique_ratio, config
            )

    if confidence < config.min_confidence and role is not ColumnRole.UNKNOWN:
        reasons = [
            *reasons,
            f"confidence {confidence:.2f} is below min_confidence "
            f"({config.min_confidence}); demoted to unknown rather than guessed",
        ]
        role = ColumnRole.UNKNOWN

    is_time_like = role is ColumnRole.DATETIME or (
        role is ColumnRole.ORDINAL and _name_matches(name, TIME_NAME_TOKENS)
    )
    levels = (
        sorted(str(value) for value in non_null.unique())
        if role in {ColumnRole.CATEGORICAL, ColumnRole.ORDINAL}
        else []
    )
    return ColumnProfile(
        name=name,
        role=role,
        dtype=dtype,
        confidence=confidence,
        n_non_null=n_non_null,
        n_unique=n_unique,
        unique_ratio=unique_ratio,
        missing_ratio=missing_ratio,
        is_time_like=is_time_like,
        levels=levels,
        usable_for_hypotheses=role in USABLE_ROLES and confidence >= config.min_confidence,
        reasons=reasons,
    )


def infer_schema(
    frame: pd.DataFrame,
    config: SchemaInferenceConfig,
    *,
    refiner: SemanticRefiner | None = None,
) -> SchemaProfile:
    """Infer every column's role from `frame`'s values.

    Guarantees: one profile per column, in the frame's column order; the frame is
    never modified; the result is deterministic for a given `(frame, config)` when no
    refiner is supplied. No column is classified into a usable role on confidence
    below `config.min_confidence`, so a consumer honouring `usable_for_hypotheses`
    cannot build a claim on a guess.

    `refiner` is the Gemma seam. It is offered only the columns the heuristics left
    `UNKNOWN` -- that is `use_llm_for_ambiguous_only` -- and only when that setting is
    on. A role it returns is recorded with `min_confidence` exactly: believed enough
    to use, never promoted above the bar the heuristics had to clear. A refiner that
    returns a nonsense role, or raises, leaves the column `UNKNOWN`; an untrusted
    helper cannot widen what this module is willing to propose.
    """
    profiles: dict[str, ColumnProfile] = {}
    for column in frame.columns:
        name = str(column)
        profile = infer_column(frame[column], name, config)
        if (
            profile.role is ColumnRole.UNKNOWN
            and refiner is not None
            and config.use_llm_for_ambiguous_only
            and profile.n_non_null >= config.min_non_null
        ):
            profile = _apply_refiner(profile, refiner, config)
        profiles[name] = profile

    return SchemaProfile(
        n_rows=int(len(frame)), n_columns=int(len(frame.columns)), columns=profiles
    )


def _apply_refiner(
    profile: ColumnProfile, refiner: SemanticRefiner, config: SchemaInferenceConfig
) -> ColumnProfile:
    """Let the refiner place one ambiguous column, failing closed on anything odd.

    A refiner that raises, returns `None`, or returns something that is not a usable
    `ColumnRole` leaves the column exactly as the heuristics left it. Its failure
    modes are the local model's, not this module's, and none of them may end in a
    column being used.
    """
    try:
        suggested = refiner.refine(profile)
    except Exception as error:  # noqa: BLE001 -- an unhelpful refiner must not fail the run
        return profile.model_copy(
            update={"reasons": [*profile.reasons, f"semantic refiner raised {error!r}; unchanged"]}
        )

    if suggested is None:
        return profile.model_copy(
            update={"reasons": [*profile.reasons, "semantic refiner declined to classify"]}
        )
    if suggested not in USABLE_ROLES:
        return profile.model_copy(
            update={
                "reasons": [
                    *profile.reasons,
                    f"semantic refiner returned {suggested!r}, which is not a usable role; "
                    f"left unknown",
                ]
            }
        )
    return profile.model_copy(
        update={
            "role": suggested,
            "confidence": config.min_confidence,
            "usable_for_hypotheses": True,
            "reasons": [
                *profile.reasons,
                f"semantic refiner ({config.model}) classified this as {suggested.value}",
            ],
        }
    )


def schema_profile(
    frame: pd.DataFrame,
    config: SchemaInferenceConfig,
    *,
    refiner: SemanticRefiner | None = None,
) -> dict[str, object]:
    """`infer_schema` as a plain JSON-serialisable mapping, for logs and API payloads.

    Guarantees: round-trips through JSON unchanged -- every value is a string, number,
    boolean, list or mapping, because `ColumnRole` is a `StrEnum`.
    """
    return infer_schema(frame, config, refiner=refiner).model_dump(mode="json")


def describe_unusable(profile: SchemaProfile) -> list[str]:
    """One human-readable line per column candidate generation will skip, and why.

    Guarantees: a line for every column with `usable_for_hypotheses=False`, so a
    silent exclusion cannot happen -- the skip is reportable, which is what makes
    failing closed reviewable rather than merely safe.
    """
    return [
        f"{name}: {column.role.value} (confidence {column.confidence:.2f}) -- "
        f"{'; '.join(column.reasons)}"
        for name, column in profile.columns.items()
        if not column.usable_for_hypotheses
    ]


def columns_for(profile: SchemaProfile, roles: Sequence[ColumnRole]) -> list[str]:
    """Usable columns carrying any of `roles`, in the frame's column order."""
    return profile.usable(*roles)
