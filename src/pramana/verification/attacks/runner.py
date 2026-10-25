"""The seven attacks, run in trusted code on the confirmation rows (PLAN §7.2).

Every attack recomputes the SAME effect the gate measured (`ClaimView.effect`) on an
altered version of the rows and compares it with the original:

  A1 outlier robustness       trim the extreme tails of each claim column
  A2 split-half replication   early vs late periods (time data) or two random halves
  A3 third-variable control   partial out the column most associated with both sides
  A4 subgroup consistency     the effect inside each level of a grouping column
  A5 alternative statistic    the other family of the same metric must agree in sign
  A6 detrend                  period-to-period changes for grouped time data
  A7 identity / leakage       one column is an exact function of the others

Attacks judge CONSISTENCY, never subgroup significance (D9): a small subgroup is not
punished for having fewer rows, only for pointing the other way or collapsing. All
thresholds come from `configs/verification.yaml` under `attacks:` and are PROVISIONAL
until calibrated against the planted cases in `tests/unit/verification/test_attacks.py`.

Owner: P.P. Satya Karthikeya
Scope: PLAN_analysis_platform.md P5
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from pramana.contracts.attack import AttackOutcome, AttackResult
from pramana.contracts.enums import ClaimType, PermutationScheme
from pramana.verification.stats.effect_size import (
    cliffs_delta,
    epsilon_squared,
    hedges_g,
    kendall_tau_b,
    pearson_r,
    sens_slope,
    spearman_rho,
)

#: The reserved period column (`verification/schemes.py`); repeated here so this module
#: does not import the scheme module, which imports the config that imports this one.
PERIOD_COLUMN = "__pramana_period__"

_NAMES = {
    "A1": "Outlier robustness",
    "A2": "Split-half replication",
    "A3": "Third-variable control",
    "A4": "Subgroup consistency",
    "A5": "Alternative statistic",
    "A6": "Detrend",
    "A7": "Identity check",
}


class AttacksConfig(BaseModel):
    """Attack thresholds (PLAN §7.2). PROVISIONAL until calibrated; no defaults."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trim_fraction: float = Field(gt=0.0, lt=0.25)
    outlier_z: float = Field(gt=0.0)
    shrink_fraction: float = Field(gt=0.0, lt=1.0)
    min_subgroup_n: int = Field(ge=5)
    min_half_periods: int = Field(ge=4)
    subgroup_weight_floor: float = Field(gt=0.0, lt=1.0)
    max_subgroup_columns: int = Field(ge=0)
    max_subgroup_levels: int = Field(ge=2)
    min_confound_score: float = Field(ge=0.0, lt=1.0)
    #: A column whose rank correlation with either side of the claim reaches this is a
    #: near-copy of that side (cost ~ revenue), not a third variable: partialling it out
    #: removes that side's own variation, so it cannot tell a confounder from a copy.
    max_control_proxy: float = Field(gt=0.0, le=1.0)
    identity_tolerance: float = Field(gt=0.0, lt=0.1)
    #: How A2 decides a half has collapsed. `point` (the original rule): the worse half's
    #: point estimate falls below `shrink_fraction` of the full estimate. `interval`: the
    #: claim is broken only when even the optimistic end of a half's interval is below that
    #: line, so a half that is merely noisy is "too noisy to tell", neither survived nor broken.
    #: `interval` breaks fewer claims than `point`; it ships OFF until the report card's
    #: false-survive rows have been read by the verification owner. Where no interval exists (a
    #: block-differenced series) `interval` falls back to `point` and says so in `details.fallback`.
    break_rule: Literal["point", "interval"]
    #: Interval rule: the nominal level of each half's bound (one-sided at kappa / 2). It is an
    #: upper bound, not the rate you get: the report card measured A2 false kill of 0.1% at 0.10
    #: and 0.8% at 0.40.
    false_kill_budget: float = Field(gt=0.0, lt=0.5)
    #: Interval rule: bootstrap resamples per half.
    damage_resamples: int = Field(ge=200, le=5000)
    #: Fewer checks than this survived-or-broken: the claim is shown as "little checked".
    min_capacity: int = Field(ge=1, le=7)
    #: S8: a model may suggest EXTRA controls and grouping columns (never fewer checks).
    #: Off by default; needs DeepSeek and Langfuse, and fails closed to the default checks.
    refuter_enabled: bool
    refuter_max_controls: int = Field(ge=0, le=5)
    refuter_max_groups: int = Field(ge=0, le=5)


@dataclass(frozen=True)
class ClaimView:
    """What was tested, in the form an attack needs to recompute its effect."""

    claim_type: ClaimType
    var_x: str
    var_y: str
    scheme: PermutationScheme
    entity_column: str | None = None
    reference_group: str | None = None
    #: True when the gate's metric has no sign (epsilon-squared for k groups).
    unsigned: bool = False

    @property
    def ordered(self) -> bool:
        return self.scheme is PermutationScheme.BLOCK_DIFFERENCED

    def numeric_columns(self) -> list[str]:
        if self.claim_type is ClaimType.GROUP_DIFFERENCE:
            return [self.var_y]
        if self.claim_type is ClaimType.TREND:
            return [self.var_y]
        return [self.var_x, self.var_y]

    # -- the gate's effect, recomputed on any subset of rows ------------------

    def effect(self, rows: pd.DataFrame) -> float | None:
        """The effect the gate gated on, for `rows`; None when it cannot be computed."""
        try:
            if self.claim_type is ClaimType.GROUP_DIFFERENCE:
                return self._group_effect(rows)
            if self.ordered:
                series = self._period_means(rows)
                if series is None:
                    return None
                if self.claim_type is ClaimType.TREND:
                    order = np.arange(len(series), dtype=float)
                    return float(kendall_tau_b(order, series[self.var_y].to_numpy(float)))
                dx = np.diff(series[self.var_x].to_numpy(float))
                dy = np.diff(series[self.var_y].to_numpy(float))
                return float(spearman_rho(dx, dy)) if dx.size >= 3 else None
            pair = _numeric(rows, [self.var_x, self.var_y])
            if len(pair) < 3:
                return None
            metric = kendall_tau_b if self.claim_type is ClaimType.TREND else spearman_rho
            return float(metric(pair[self.var_x].to_numpy(), pair[self.var_y].to_numpy()))
        except (ValueError, ZeroDivisionError, FloatingPointError):
            return None

    def alternative(self, rows: pd.DataFrame) -> tuple[str, float | None]:
        """The other family of statistic for A5, and its value."""
        try:
            if self.claim_type is ClaimType.GROUP_DIFFERENCE:
                groups = self._groups(rows)
                if groups is None or len(groups) != 2:
                    return "hedges_g", None
                return "hedges_g", float(hedges_g(groups[0], groups[1]))
            if self.ordered:
                series = self._period_means(rows)
                if series is None:
                    return "pearson_r", None
                if self.claim_type is ClaimType.TREND:
                    values = series[self.var_y].to_numpy(float)
                    return "sens_slope", float(
                        sens_slope(np.arange(values.size, dtype=float), values)
                    )
                dx = np.diff(series[self.var_x].to_numpy(float))
                dy = np.diff(series[self.var_y].to_numpy(float))
                return "pearson_r_of_changes", float(pearson_r(dx, dy))
            pair = _numeric(rows, [self.var_x, self.var_y])
            x, y = pair[self.var_x].to_numpy(), pair[self.var_y].to_numpy()
            if self.claim_type is ClaimType.TREND:
                return "sens_slope", float(sens_slope(x, y))
            return "pearson_r", float(pearson_r(x, y))
        except (ValueError, ZeroDivisionError, FloatingPointError):
            return "alternative", None

    @property
    def signed(self) -> bool:
        return not self.unsigned

    def _period_means(self, rows: pd.DataFrame) -> pd.DataFrame | None:
        names = [self.var_y] if self.claim_type is ClaimType.TREND else [self.var_x, self.var_y]
        if PERIOD_COLUMN not in rows.columns:
            return None
        data = _numeric(rows, [PERIOD_COLUMN, *names])
        series = data.groupby(PERIOD_COLUMN)[names].mean().sort_index()
        return series if len(series) >= 4 else None

    def _labels(self, rows: pd.DataFrame) -> list[str]:
        labels = sorted(rows[self.var_x].dropna().astype(str).unique().tolist())
        reference = self.reference_group
        if reference is not None and reference not in labels:
            # The same level written differently ("1" against "1.0"), as the template does.
            same = [n for n in labels if _same_level(n, reference)]
            reference = same[0] if len(same) == 1 else None
        if reference is not None:
            labels = [reference] + [n for n in labels if n != reference]
        return labels

    def _groups(self, rows: pd.DataFrame) -> list[np.ndarray] | None:
        data = rows[[self.var_x, self.var_y]].copy()
        data[self.var_y] = pd.to_numeric(data[self.var_y], errors="coerce")
        data = data.dropna()
        groups = [
            data.loc[data[self.var_x].astype(str) == name, self.var_y].to_numpy(float)
            for name in self._labels(data)
        ]
        if len(groups) < 2 or any(g.size < 2 for g in groups):
            return None
        return groups

    def _group_effect(self, rows: pd.DataFrame) -> float | None:
        groups = self._groups(rows)
        if groups is None:
            return None
        if len(groups) == 2:
            return float(cliffs_delta(groups[0], groups[1]))
        return float(epsilon_squared(groups))


@dataclass(frozen=True)
class AttackHints:
    """Extra columns an advisor suggests trying. They can only ADD checks (design v3, S8).

    `controls` are extra third-variable controls for A3 and `groups` extra subgroup
    columns for A4. An unknown or unusable name is ignored; an empty hint changes nothing.
    """

    controls: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()


def _numeric(rows: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    return rows[names].apply(pd.to_numeric, errors="coerce").dropna()


def _sign(value: float) -> int:
    return 0 if abs(value) < 1e-12 else (1 if value > 0 else -1)


def _collapsed(original: float, attacked: float, config: AttacksConfig, signed: bool) -> bool:
    """Sign flip (signed metrics) or shrinkage past the configured fraction."""
    if signed and _sign(attacked) == -_sign(original):
        return True
    return abs(attacked) < config.shrink_fraction * abs(original)


def _result(
    attack_id: str,
    outcome: AttackOutcome,
    reason: str,
    *,
    original: float | None = None,
    attacked: float | None = None,
    n_rows: int | None = None,
    applicable: bool = True,
    **details: float | int | str | bool | None,
) -> AttackResult:
    return AttackResult(
        attack_id=attack_id,
        name=_NAMES[attack_id],
        outcome=outcome,
        reason=reason,
        original_effect=original,
        attacked_effect=None if outcome is AttackOutcome.NOT_RUN else attacked,
        n_rows=n_rows,
        applicable=applicable,
        details=details,
    )


def _not_run(attack_id: str, reason: str, *, applicable: bool = True) -> AttackResult:
    """A result for an attack that did not run; `applicable=False` when it cannot apply here."""
    return _result(attack_id, AttackOutcome.NOT_RUN, reason, applicable=applicable)


def _verdict(
    attack_id: str,
    claim: ClaimView,
    original: float,
    attacked: float | None,
    config: AttacksConfig,
    *,
    what: str,
    n_rows: int,
    **details: float | int | str | bool | None,
) -> AttackResult:
    if attacked is None:
        return _not_run(attack_id, f"the effect could not be computed {what}")
    if _collapsed(original, attacked, config, claim.signed):
        flipped = claim.signed and _sign(attacked) == -_sign(original)
        how = "reverses" if flipped else "shrinks"
        return _result(
            attack_id,
            AttackOutcome.BROKEN,
            f"the effect {how} {what} ({original:+.3f} -> {attacked:+.3f})",
            original=original,
            attacked=attacked,
            n_rows=n_rows,
            **details,
        )
    return _result(
        attack_id,
        AttackOutcome.SURVIVED,
        f"the effect holds {what} ({original:+.3f} -> {attacked:+.3f})",
        original=original,
        attacked=attacked,
        n_rows=n_rows,
        **details,
    )


# --- A1 -----------------------------------------------------------------------


def _robust_z(values: pd.Series) -> pd.Series:
    """|x - median| / (1.4826 * MAD); 0 for a column with no spread."""
    centre = values.median()
    mad = float((values - centre).abs().median()) * 1.4826
    if not np.isfinite(mad) or mad == 0.0:
        return pd.Series(0.0, index=values.index)
    return ((values - centre).abs() / mad).fillna(0.0)


def _a1_trim(claim: ClaimView, rows: pd.DataFrame, original: float, config: AttacksConfig):
    """Drop rows that are extreme on a claim column, then recompute.

    Only rows beyond `outlier_z` robust z-scores go, the most extreme first, and never
    more than `trim_fraction` of the rows. Cutting fixed tails off well-behaved data
    would weaken a real correlation by construction (restriction of range) and count
    that as fragility; here a Gaussian table loses almost nothing and survives, while
    an effect made by a few extreme points loses them.
    """
    score = pd.Series(0.0, index=rows.index)
    for name in claim.numeric_columns():
        score = np.maximum(score, _robust_z(pd.to_numeric(rows[name], errors="coerce")))
    extreme = score[score > config.outlier_z].sort_values(ascending=False)
    cap = int(np.floor(config.trim_fraction * len(rows)))
    dropped = extreme.index[:cap]
    if len(dropped) == 0:
        return _result(
            "A1",
            AttackOutcome.SURVIVED,
            f"no row is beyond {config.outlier_z:g} robust z-scores on a claim column",
            original=original,
            attacked=original,
            n_rows=int(len(rows)),
        )
    trimmed = rows.drop(index=dropped)
    return _verdict(
        "A1",
        claim,
        original,
        claim.effect(trimmed),
        config,
        what=f"with the {len(dropped)} most extreme rows removed",
        n_rows=int(len(trimmed)),
        removed=int(len(dropped)),
    )


# --- A2 -----------------------------------------------------------------------


def _a2_halves(
    claim: ClaimView, rows: pd.DataFrame, original: float, config: AttacksConfig, seed: int
):
    if PERIOD_COLUMN in rows.columns and rows[PERIOD_COLUMN].notna().any():
        periods = np.sort(rows[PERIOD_COLUMN].dropna().unique())
        if claim.ordered and len(periods) < 2 * config.min_half_periods:
            return _not_run("A2", f"{len(periods)} periods is too few to split in two halves")
        cut = periods[len(periods) // 2]
        halves = [rows[rows[PERIOD_COLUMN] < cut], rows[rows[PERIOD_COLUMN] >= cut]]
        label = "in the earlier and the later half of the periods"
    else:
        order = np.random.default_rng(seed).permutation(len(rows))
        mid = len(rows) // 2
        halves = [rows.iloc[order[:mid]], rows.iloc[order[mid:]]]
        label = "in two random halves of the rows"
    if not claim.ordered and min(len(h) for h in halves) < config.min_subgroup_n:
        return _not_run("A2", f"each half needs {config.min_subgroup_n} rows")
    effects = [claim.effect(h) for h in halves]
    if any(e is None for e in effects):
        return _not_run("A2", "the effect could not be computed in one of the halves")
    if config.break_rule == "interval":
        judged = _a2_interval(claim, halves, effects, original, config, seed, label, len(rows))
        if judged is not None:
            return judged
        # no interval for this scheme (a block-differenced series): say so, use the point rule
    worst = min(effects, key=lambda e: e * _sign(original) if claim.signed else abs(e))
    return _verdict(
        "A2",
        claim,
        original,
        worst,
        config,
        what=label,
        n_rows=int(len(rows)),
        first_half=effects[0],
        second_half=effects[1],
        **({"fallback": "point rule: no interval for this scheme"}
           if config.break_rule == "interval" else {}),
    )


def _a2_interval(
    claim: ClaimView,
    halves: list[pd.DataFrame],
    effects: list[float],
    original: float,
    config: AttacksConfig,
    seed: int,
    label: str,
    n_rows: int,
):
    """A2 on evidence: broken only if a half's interval lies wholly below the collapse line.

    The line is `shrink_fraction` of the full effect, in the original's direction. A half
    whose point estimate is below the line but whose interval still reaches it is not proof
    of anything: it is returned as not run with `too_noisy`, which counts for neither side.
    """
    from pramana.verification.interval import effect_interval  # interval imports this package

    line = config.shrink_fraction * abs(original)
    toward = 1.0 if (not claim.signed or _sign(original) >= 0) else -1.0
    confidence = 1.0 - config.false_kill_budget  # two-sided 1 - kappa: one-sided kappa / 2 per half
    worst = min(effects, key=lambda e: e * _sign(original) if claim.signed else abs(e))
    uppers: list[float] = []
    for i, half in enumerate(halves):
        found = effect_interval(
            claim, half, n_resamples=config.damage_resamples, confidence=confidence, seed=seed + i
        )
        if found is None:  # no interval for this scheme or half: the caller uses the point rule
            return None
        uppers.append(max(found.high * toward, found.low * toward))
    details = dict(first_half=effects[0], second_half=effects[1], bound_first=uppers[0],
                   bound_second=uppers[1], false_kill_budget=config.false_kill_budget)
    if any(u < line for u in uppers):
        return _result("A2", AttackOutcome.BROKEN,
                       f"the effect collapses {label} even at the optimistic end of its interval "
                       f"({original:+.3f} -> {worst:+.3f})",
                       original=original, attacked=worst, n_rows=n_rows, **details)
    if _collapsed(original, worst, config, claim.signed):
        return _result("A2", AttackOutcome.NOT_RUN,
                       f"too noisy to tell: the effect is smaller {label} ({original:+.3f} -> "
                       f"{worst:+.3f}) but its interval still reaches the collapse line",
                       n_rows=n_rows, too_noisy=True, **details)
    return _result(
        "A2", AttackOutcome.SURVIVED,
        f"the effect holds {label} ({original:+.3f} -> {worst:+.3f})",
        original=original, attacked=worst, n_rows=n_rows, **details,
    )


# --- A3 -----------------------------------------------------------------------


def _ranks(values: pd.Series) -> np.ndarray:
    return values.rank().to_numpy(float)


def _residual(target: np.ndarray, control: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones_like(control), control])
    coef, *_ = np.linalg.lstsq(design, target, rcond=None)
    return target - design @ coef


def _candidate_controls(claim: ClaimView, rows: pd.DataFrame) -> list[str]:
    taken = {claim.var_x, claim.var_y, PERIOD_COLUMN, claim.entity_column}
    out = []
    for name in rows.columns:
        if name in taken:
            continue
        values = pd.to_numeric(rows[name], errors="coerce")
        if values.notna().sum() < 10 or values.nunique() < 3:
            continue
        if values.nunique() == values.notna().sum() and (values.diff().dropna() == 1).all():
            continue  # a row counter
        out.append(name)
    return out


def _a3_score(
    claim: ClaimView, rows: pd.DataFrame, name: str, config: AttacksConfig
) -> float | None:
    """How strongly `name` could confound the claim, or None when it cannot be used."""
    if claim.claim_type is ClaimType.CORRELATION:
        data = _numeric(rows, [claim.var_x, claim.var_y, name])
        if len(data) < config.min_subgroup_n:
            return None
        with_x = abs(spearman_rho(data[claim.var_x], data[name]))
        with_y = abs(spearman_rho(data[claim.var_y], data[name]))
        if max(with_x, with_y) >= config.max_control_proxy:
            return None  # a near-copy of one side, not a third variable (see AttacksConfig)
        return float(with_x * with_y)
    data = rows[[claim.var_x, claim.var_y, name]].copy()
    data[[claim.var_y, name]] = data[[claim.var_y, name]].apply(pd.to_numeric, errors="coerce")
    data = data.dropna()
    if len(data) < config.min_subgroup_n:
        return None
    by_label = [g[name].to_numpy(float) for _, g in data.groupby(claim.var_x) if len(g) >= 2]
    if len(by_label) < 2:
        return None
    with_y = abs(spearman_rho(data[claim.var_y], data[name]))
    if with_y >= config.max_control_proxy:
        return None  # a near-copy of the measure, not a third variable
    return float(np.sqrt(epsilon_squared(by_label)) * with_y)


def _a3_apply(
    claim: ClaimView,
    rows: pd.DataFrame,
    original: float,
    config: AttacksConfig,
    control: str,
    score: float,
) -> AttackResult:
    """The effect after accounting for `control`, judged like every other attack."""
    if claim.claim_type is ClaimType.CORRELATION:
        data = _numeric(rows, [claim.var_x, claim.var_y, control])
        z = _ranks(data[control])
        rx = _residual(_ranks(data[claim.var_x]), z)
        ry = _residual(_ranks(data[claim.var_y]), z)
        attacked = float(pearson_r(rx, ry))
    else:
        data = rows[[claim.var_x, claim.var_y, control]].copy()
        data[control] = pd.to_numeric(data[control], errors="coerce")
        data = data.dropna()
        strata = pd.qcut(data[control].rank(method="first"), 4, labels=False)
        effects, weights = [], []
        for _, part in data.groupby(strata):
            value = claim.effect(part)
            if value is not None:
                effects.append(value)
                weights.append(len(part))
        attacked = float(np.average(effects, weights=weights)) if effects else None
    return _verdict(
        "A3",
        claim,
        original,
        attacked,
        config,
        what=f"after accounting for {control!r}",
        n_rows=int(len(data)),
        control=control,
        confound_score=round(score, 4),
    )


def _a3_control(
    claim: ClaimView,
    rows: pd.DataFrame,
    original: float,
    config: AttacksConfig,
    hints: AttackHints | None = None,
):
    if claim.claim_type is ClaimType.TREND or claim.ordered:
        return _not_run(
            "A3", "a trend over time has no third-variable control here", applicable=False
        )
    usable = _candidate_controls(claim, rows)
    best: tuple[float, str] | None = None
    scores: dict[str, float] = {}
    for name in usable:
        score = _a3_score(claim, rows, name, config)
        if score is None:
            continue
        scores[name] = score
        if best is None or score > best[0]:
            best = (score, name)
    controls: list[tuple[float, str]] = []
    if best is not None and best[0] >= config.min_confound_score:
        controls.append(best)
    # A suggested control is ADDED to the strongest one, never swapped for it, and it must
    # clear the same near-copy screen: suggestions can only widen what is tried.
    for name in (hints.controls if hints else ()):
        if name in scores and all(name != c for _, c in controls):
            controls.append((scores[name], name))
    if not controls:
        return _not_run(
            "A3",
            "no other column is associated with both sides of the claim",
            applicable=False,
        )
    results = [_a3_apply(claim, rows, original, config, c, s) for s, c in controls]
    return next((r for r in results if r.outcome is AttackOutcome.BROKEN), results[0])


# --- A4 -----------------------------------------------------------------------


def _grouping_columns(claim: ClaimView, rows: pd.DataFrame, config: AttacksConfig) -> list[str]:
    taken = {claim.var_x, claim.var_y, PERIOD_COLUMN}
    out = []
    for name in rows.columns:
        if name in taken:
            continue
        levels = rows[name].dropna()
        n_levels = levels.nunique()
        numeric = pd.api.types.is_numeric_dtype(rows[name])
        if 2 <= n_levels <= config.max_subgroup_levels and (not numeric or n_levels <= 5):
            out.append(name)
    return out[: config.max_subgroup_columns]


def _is_grouping(claim: ClaimView, rows: pd.DataFrame, name: str, config: AttacksConfig) -> bool:
    """A suggested grouping column is usable on the same terms as an automatic one."""
    if name not in rows.columns or name in {claim.var_x, claim.var_y, PERIOD_COLUMN}:
        return False
    n_levels = rows[name].dropna().nunique()
    numeric = pd.api.types.is_numeric_dtype(rows[name])
    return 2 <= n_levels <= config.max_subgroup_levels and (not numeric or n_levels <= 5)


def _a4_subgroups(
    claim: ClaimView,
    rows: pd.DataFrame,
    original: float,
    config: AttacksConfig,
    hints: AttackHints | None = None,
):
    if not claim.signed:
        return _not_run("A4", "the effect has no direction to reverse", applicable=False)
    if claim.ordered:
        return _not_run("A4", "a single ordered series has no subgroups", applicable=False)
    columns = _grouping_columns(claim, rows, config)
    for name in (hints.groups if hints else ()):
        if name not in columns and _is_grouping(claim, rows, name, config):
            columns.append(name)
    if not columns:
        return _not_run("A4", "no grouping column with a few levels", applicable=False)
    checked = 0
    for name in columns:
        effects, weights, labels = [], [], []
        for level, part in rows.groupby(rows[name].astype(str)):
            if len(part) < config.min_subgroup_n:
                continue
            value = claim.effect(part)
            if value is None:
                continue
            effects.append(value)
            weights.append(len(part) / len(rows))
            labels.append(level)
        if len(effects) < 2:
            continue
        checked += 1
        for value, weight, level in zip(effects, weights, labels, strict=True):
            if (
                weight >= config.subgroup_weight_floor
                and _sign(value) == -_sign(original)
                and abs(value) >= config.shrink_fraction * abs(original)
            ):
                return _result(
                    "A4",
                    AttackOutcome.BROKEN,
                    f"the effect reverses where {name} = {level!r} "
                    f"({weight:.0%} of rows: {original:+.3f} -> {value:+.3f})",
                    original=original,
                    attacked=value,
                    n_rows=int(round(weight * len(rows))),
                    column=name,
                    level=level,
                )
        pooled_within = float(np.average(effects, weights=weights))
        if _sign(pooled_within) == -_sign(original):
            return _result(
                "A4",
                AttackOutcome.BROKEN,
                f"within the levels of {name} the effect points the other way "
                f"({original:+.3f} overall, {pooled_within:+.3f} within)",
                original=original,
                attacked=pooled_within,
                n_rows=int(len(rows)),
                column=name,
            )
    if checked == 0:
        return _not_run("A4", f"no subgroup has {config.min_subgroup_n} rows")
    return _result(
        "A4",
        AttackOutcome.SURVIVED,
        f"the effect points the same way within the levels of {', '.join(columns)}",
        original=original,
        n_rows=int(len(rows)),
        columns=", ".join(columns),
    )


# --- A5 -----------------------------------------------------------------------


def _a5_alternative(claim: ClaimView, rows: pd.DataFrame, original: float):
    if not claim.signed:
        return _not_run("A5", "an unsigned effect has no alternative sign to compare", applicable=False)
    name, value = claim.alternative(rows)
    if value is None:
        return _not_run("A5", f"{name} could not be computed")
    if _sign(value) == -_sign(original):
        return _result(
            "A5",
            AttackOutcome.BROKEN,
            f"{name} points the other way ({value:+.3f}) from the tested effect ({original:+.3f})",
            original=original,
            attacked=value,
            n_rows=int(len(rows)),
            statistic=name,
        )
    return _result(
        "A5",
        AttackOutcome.SURVIVED,
        f"{name} agrees in sign ({value:+.3f})",
        original=original,
        attacked=value,
        n_rows=int(len(rows)),
        statistic=name,
    )


# --- A6 -----------------------------------------------------------------------


def _a6_detrend(claim: ClaimView, rows: pd.DataFrame, original: float, config: AttacksConfig):
    if claim.claim_type is not ClaimType.CORRELATION:
        return _not_run("A6", "only an association between two columns can be detrended", applicable=False)
    if claim.ordered:
        return _not_run("A6", "already tested on period-to-period changes", applicable=False)
    if PERIOD_COLUMN not in rows.columns:
        return _not_run("A6", "the rows are not time-ordered", applicable=False)
    keys = [claim.entity_column] if claim.entity_column else []
    data = rows[[*keys, PERIOD_COLUMN, claim.var_x, claim.var_y]].copy()
    data[[claim.var_x, claim.var_y]] = data[[claim.var_x, claim.var_y]].apply(
        pd.to_numeric, errors="coerce"
    )
    data = data.dropna()
    means = data.groupby([*keys, PERIOD_COLUMN])[[claim.var_x, claim.var_y]].mean().sort_index()
    changes = means.groupby(level=0).diff() if keys else means.diff()
    changes = changes.dropna()
    if len(changes) < config.min_subgroup_n:
        return _not_run("A6", f"{len(changes)} period-to-period changes is too few")
    attacked = float(spearman_rho(changes[claim.var_x], changes[claim.var_y]))
    return _verdict(
        "A6",
        claim,
        original,
        attacked,
        config,
        what="on period-to-period changes",
        n_rows=int(len(changes)),
    )


# --- A7 -----------------------------------------------------------------------


def _a7_identity(claim: ClaimView, rows: pd.DataFrame, original: float, config: AttacksConfig):
    if claim.claim_type is not ClaimType.CORRELATION:
        return _not_run("A7", "only a pair of numeric columns can be an identity", applicable=False)
    data = _numeric(rows, [claim.var_x, claim.var_y])
    if len(data) < 3:
        return _not_run("A7", "too few rows")
    x, y = data[claim.var_x].to_numpy(float), data[claim.var_y].to_numpy(float)
    scale = float(np.std(y)) or 1.0
    if abs(pearson_r(x, y)) >= 1 - config.identity_tolerance**2:
        return _result(
            "A7",
            AttackOutcome.BROKEN,
            f"{claim.var_y!r} is an exact linear function of {claim.var_x!r}",
            original=original,
            n_rows=int(len(data)),
        )
    for name in _candidate_controls(claim, rows):
        z = pd.to_numeric(rows.loc[data.index, name], errors="coerce").to_numpy(float)
        ok = ~np.isnan(z)
        if ok.sum() < 3:
            continue
        for label, combined in (
            (f"{claim.var_x} + {name}", x + z),
            (f"{claim.var_x} - {name}", x - z),
            (f"{name} - {claim.var_x}", z - x),
        ):
            if float(np.max(np.abs(combined[ok] - y[ok]))) <= config.identity_tolerance * scale:
                return _result(
                    "A7",
                    AttackOutcome.BROKEN,
                    f"{claim.var_y!r} equals {label} exactly, so the association is arithmetic",
                    original=original,
                    n_rows=int(ok.sum()),
                    column=name,
                )
    return _result(
        "A7",
        AttackOutcome.SURVIVED,
        "no exact identity between the columns",
        original=original,
        n_rows=int(len(data)),
    )


def run_attacks(
    claim: ClaimView,
    rows: pd.DataFrame,
    config: AttacksConfig,
    *,
    seed: int,
    hints: AttackHints | None = None,
) -> list[AttackResult]:
    """Run A1..A7 on `rows` (the confirmation rows with the period column).

    Guarantees: one result per attack, in A1..A7 order; an attack that raises is
    recorded as NOT_RUN with the error, never as survived; nothing here reads a
    p-value or changes a verdict -- the caller applies the ratchet.
    """
    if claim.claim_type in (ClaimType.PERIOD_CHANGE, ClaimType.SEASONALITY):
        return [
            _not_run(
                a,
                f"no attack is defined yet for a {claim.claim_type.value} claim",
                applicable=False,
            )
            for a in _NAMES
        ]
    original = claim.effect(rows)
    if original is None or _sign(original) == 0:
        return [_not_run(a, "the tested effect could not be recomputed") for a in _NAMES]
    steps: list[tuple[str, Callable[[], AttackResult]]] = [
        ("A1", lambda: _a1_trim(claim, rows, original, config)),
        ("A2", lambda: _a2_halves(claim, rows, original, config, seed)),
        ("A3", lambda: _a3_control(claim, rows, original, config, hints)),
        ("A4", lambda: _a4_subgroups(claim, rows, original, config, hints)),
        ("A5", lambda: _a5_alternative(claim, rows, original)),
        ("A6", lambda: _a6_detrend(claim, rows, original, config)),
        ("A7", lambda: _a7_identity(claim, rows, original, config)),
    ]
    results = []
    for attack_id, step in steps:
        try:
            results.append(step())
        except Exception as error:  # an attack that fails to run is not a survival
            results.append(
                _not_run(attack_id, f"the attack failed to run ({type(error).__name__})")
            )
    return results


def _same_level(label: str, wanted: str) -> bool:
    """Whether two labels name the same group level ("1" and "1.0", " A" and "a")."""
    try:
        return float(label) == float(wanted)
    except ValueError:
        return label.strip().casefold() == wanted.strip().casefold()
