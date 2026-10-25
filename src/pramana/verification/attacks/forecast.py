"""The six attacks on a forecast claim that passed the gate (F1-F6).

A forecast claim says: on the periods it did not see, this method was closer than a baseline.
Each attack asks whether that survives being looked at another way, on the SAME backtest the
gate scored (no refitting, so no attack can see more than the gate's origins):

  F1 leave out origins      drop each origin in turn, and the best tenth: still better?
  F2 recent origins only    only the most recent third: guards against a method that worked
                            long ago and no longer does
  F3 every horizon          a method good one period ahead and worse two periods ahead does
                            not hold up for "the next two months"
  F4 interval calibration   the stated prediction range, built on the earlier origins, must
                            cover about its nominal share of the later ones
  F5 structural break       a break in the method's one-step errors inside the held-back
                            window, then whether its advantage survives after the break
  F6 outlier months         drop origins whose loss is an outlier for either forecast

A one-way ratchet: BROKEN lowers a PASS to FRAGILE, nothing here raises anything. An attack
that cannot be judged says so (`NOT_RUN`, with `applicable` telling "does not exist for this
claim" from "could not run on these rows"). F4 changes the wording and not the verdict unless
`forecast.attacks.calibration_changes_verdict` says so: accuracy can have held up while the
stated range is not trustworthy, and the two are different statements.

Thresholds are in `configs/verification.yaml` under `forecast.attacks` (PROVISIONAL, measured
in docs/evidence/FORECAST_CLAIM_2026-10-25.md). A broken check is not proof that the forecast
is bad: it means the backtest's advantage did not survive that check on these rows.

Owner: P.P. Satya Karthikeya
Scope: docs/evidence/FORECAST_CLAIM_2026-10-25.md
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np

from pramana.contracts.attack import AttackOutcome, AttackResult
from pramana.verification.stats.forecast import Backtest, relative_reduction

if TYPE_CHECKING:  # pragma: no cover -- config imports the attacks package, so avoid the cycle
    from pramana.verification.attacks.runner import AttacksConfig
    from pramana.verification.config import ForecastConfig

FORECAST_ATTACK_NAMES = {
    "F1": "Leave out origins",
    "F2": "Recent origins only",
    "F3": "Every horizon",
    "F4": "Interval calibration",
    "F5": "Structural break",
    "F6": "Outlier months",
}

_BREAK_NOTE = "A break is not proof the forecast is bad."


def _result(
    attack_id: str,
    outcome: AttackOutcome,
    reason: str,
    *,
    original: float | None = None,
    attacked: float | None = None,
    n_origins: int | None = None,
    applicable: bool = True,
    **details: float | int | str | bool | None,
) -> AttackResult:
    return AttackResult(
        attack_id=attack_id,
        name=FORECAST_ATTACK_NAMES[attack_id],
        outcome=outcome,
        reason=reason,
        original_effect=original,
        attacked_effect=None if outcome is AttackOutcome.NOT_RUN else attacked,
        n_rows=n_origins,
        applicable=applicable,
        details=details,
    )


def _not_run(attack_id: str, reason: str, *, applicable: bool = True) -> AttackResult:
    return _result(attack_id, AttackOutcome.NOT_RUN, reason, applicable=applicable)


def _origin_loss(loss: np.ndarray) -> np.ndarray:
    return loss.sum(axis=1)


def _reduction(model: np.ndarray, baseline: np.ndarray, keep: np.ndarray) -> float | None:
    """The reduction over the origins in `keep` (a boolean mask), or None if undefined."""
    if not keep.any():
        return None
    try:
        return relative_reduction(model[keep], baseline[keep])
    except ValueError:
        return None


def _robust_z(values: np.ndarray) -> np.ndarray:
    """One-sided robust z: (x - median) / (1.4826 MAD); zeros for a column with no spread."""
    centre = float(np.median(values))
    mad = float(np.median(np.abs(values - centre))) * 1.4826
    if not math.isfinite(mad) or mad == 0.0:
        return np.zeros_like(values)
    return (values - centre) / mad


# --- F1 -----------------------------------------------------------------------


def _f1_leave_out(test: Backtest, original: float, attacks: AttacksConfig) -> AttackResult:
    lm, lb = _origin_loss(test.model_loss), _origin_loss(test.baseline_loss)
    n = lm.size
    everyone = np.ones(n, dtype=bool)
    leave_one = [_reduction(lm, lb, np.arange(n) != i) for i in range(n)]
    worst_single = min(r for r in leave_one if r is not None)
    cap = max(1, int(round(attacks.trim_fraction * n)))
    best = np.argsort(-(lb - lm), kind="stable")[:cap]
    keep = everyone.copy()
    keep[best] = False
    trimmed = _reduction(lm, lb, keep)
    if trimmed is None:
        return _not_run("F1", "the reduction could not be computed with the best origins removed")
    attacked = min(worst_single, trimmed)
    shared = {"left_out_one_worst": worst_single, "dropped_best": int(cap)}
    if attacked <= 0.0:
        return _result(
            "F1",
            AttackOutcome.BROKEN,
            f"with the best {cap} of {n} origins removed the method is no longer better than "
            f"the baseline (error reduction {original:+.3f} -> {attacked:+.3f})",
            original=original,
            attacked=attacked,
            n_origins=n - cap,
            **shared,
        )
    return _result(
        "F1",
        AttackOutcome.SURVIVED,
        f"still better than the baseline with any one origin left out and with the best {cap} "
        f"of {n} removed (error reduction {original:+.3f} -> {attacked:+.3f})",
        original=original,
        attacked=attacked,
        n_origins=n - cap,
        **shared,
    )


# --- F2 -----------------------------------------------------------------------


def _f2_recent(test: Backtest, original: float, settings: ForecastConfig) -> AttackResult:
    rules = settings.attacks
    lm, lb = _origin_loss(test.model_loss), _origin_loss(test.baseline_loss)
    n = lm.size
    take = max(rules.min_origins_per_part, math.ceil(rules.recent_fraction * n))
    if take >= n:
        return _not_run("F2", f"only {n} origins, too few to set a recent part apart")
    recent = _reduction(lm, lb, np.arange(n) >= n - take)
    if recent is None:
        return _not_run("F2", "the reduction could not be computed on the recent origins")
    if recent <= 0.0:
        return _result(
            "F2",
            AttackOutcome.BROKEN,
            f"on the most recent {take} of {n} origins the method is no longer better than the "
            f"baseline (error reduction {original:+.3f} -> {recent:+.3f}); it may have worked "
            f"earlier and not lately",
            original=original,
            attacked=recent,
            n_origins=take,
        )
    return _result(
        "F2",
        AttackOutcome.SURVIVED,
        f"still better than the baseline on the most recent {take} of {n} origins "
        f"(error reduction {original:+.3f} -> {recent:+.3f})",
        original=original,
        attacked=recent,
        n_origins=take,
    )


# --- F3 -----------------------------------------------------------------------


def _f3_horizons(test: Backtest, original: float, settings: ForecastConfig) -> AttackResult:
    horizon = test.horizon
    if horizon < 2:
        return _not_run(
            "F3", "only one horizon was asked, so there is no other to compare", applicable=False
        )
    margin = settings.attacks.horizon_margin
    per_horizon = [
        relative_reduction(test.model_loss[:, h], test.baseline_loss[:, h]) for h in range(horizon)
    ]
    worst = int(np.argmin(per_horizon))
    shown = ", ".join(f"{h + 1}: {r:+.2f}" for h, r in enumerate(per_horizon))
    details = {"worst_horizon": worst + 1, "horizons": horizon}
    if per_horizon[worst] < -margin:
        return _result(
            "F3",
            AttackOutcome.BROKEN,
            f"{worst + 1} period{'s' if worst else ''} ahead the method is worse than the "
            f"baseline (error reduction {per_horizon[worst]:+.3f}; by horizon: {shown}), so it "
            f"does not hold up for every period asked about",
            original=original,
            attacked=float(per_horizon[worst]),
            n_origins=test.n_origins,
            **details,
        )
    return _result(
        "F3",
        AttackOutcome.SURVIVED,
        f"not worse than the baseline at any single horizon (error reduction by horizon: {shown})",
        original=original,
        attacked=float(per_horizon[worst]),
        n_origins=test.n_origins,
        **details,
    )


# --- F4 -----------------------------------------------------------------------


def stated_interval(test: Backtest, level: float) -> tuple[float, float, float, int] | None:
    """The prediction range built on the earlier half of the origins, and how it did on the later.

    Returns `(low, high, coverage, n_checked)` in scaled-error units, or None when there are too
    few origins in a half. The range is the central `level` share of the earlier half's signed
    scaled errors; coverage is the share of the later half's errors inside it.
    """
    n = test.n_origins
    half = n // 2
    if half < 2 or n - half < 2:
        return None
    signed = (test.actual - test.model) / test.scale[:, None]
    tail = (1.0 - level) / 2.0
    low, high = np.quantile(signed[:half].ravel(), [tail, 1.0 - tail])
    later = signed[half:].ravel()
    coverage = float(np.mean((later >= low) & (later <= high)))
    return float(low), float(high), coverage, int(later.size)


def _f4_calibration(test: Backtest, original: float, settings: ForecastConfig) -> AttackResult:
    level = settings.interval_level
    rules = settings.attacks
    found = stated_interval(test, level)
    if found is None:
        return _not_run("F4", "too few origins to build a range on some and check it on others")
    _, _, coverage, checked = found
    off = abs(coverage - level)
    details = {
        "nominal": level,
        "coverage": coverage,
        "checked": checked,
        "calibrated": off <= rules.interval_tolerance,
    }
    if off <= rules.interval_tolerance:
        return _result(
            "F4",
            AttackOutcome.SURVIVED,
            f"the {level * 100:.0f}% range built on the earlier origins covered "
            f"{coverage * 100:.0f}% of the later ones",
            original=original,
            attacked=original,
            n_origins=test.n_origins,
            **details,
        )
    reason = (
        f"accuracy held up, but the stated range is not calibrated: the {level * 100:.0f}% range "
        f"built on the earlier origins covered {coverage * 100:.0f}% of the later ones"
    )
    return _result(
        "F4",
        AttackOutcome.BROKEN if rules.calibration_changes_verdict else AttackOutcome.SURVIVED,
        reason,
        original=original,
        attacked=original,
        n_origins=test.n_origins,
        **details,
    )


# --- F5 -----------------------------------------------------------------------


def _f5_break(test: Backtest, original: float, settings: ForecastConfig) -> AttackResult:
    rules = settings.attacks
    lm, lb = _origin_loss(test.model_loss), _origin_loss(test.baseline_loss)
    n = lm.size
    if n < 2 * rules.min_origins_per_part:
        return _not_run("F5", f"only {n} origins, too few to look for a break")
    errors = (test.actual[:, 0] - test.model[:, 0]) / test.scale
    spread = float(errors.std(ddof=1))
    if not spread > 0.0:
        return _not_run("F5", "the one-step errors have no spread, so a break cannot be looked for")
    cusum = np.cumsum(errors - errors.mean()) / (spread * math.sqrt(n))
    peak = int(np.argmax(np.abs(cusum)))
    statistic = float(np.abs(cusum[peak]))
    details = {"cusum": statistic, "critical": rules.cusum_critical}
    if statistic <= rules.cusum_critical:
        return _result(
            "F5",
            AttackOutcome.SURVIVED,
            f"no structural break found in the method's one-step errors (CUSUM {statistic:.2f}, "
            f"below {rules.cusum_critical:.2f})",
            original=original,
            attacked=original,
            n_origins=n,
            **details,
        )
    cut = peak + 1
    if cut < rules.min_origins_per_part or n - cut < rules.min_origins_per_part:
        return _not_run(
            "F5",
            f"a break was suggested near origin {cut} of {n}, too close to an edge to compare "
            f"before and after",
        )
    after = _reduction(lm, lb, np.arange(n) >= cut)
    before = _reduction(lm, lb, np.arange(n) < cut)
    if after is None or before is None:
        return _not_run("F5", "the reduction could not be computed either side of the break")
    where = int(test.origins[cut])
    if after <= 0.0:
        return _result(
            "F5",
            AttackOutcome.BROKEN,
            f"a break was found in the method's errors from origin {cut} of {n}, and after it "
            f"the method is no longer better than the baseline (error reduction {before:+.3f} "
            f"before, {after:+.3f} after). {_BREAK_NOTE}",
            original=original,
            attacked=after,
            n_origins=n - cut,
            break_origin_index=where,
            **details,
        )
    return _result(
        "F5",
        AttackOutcome.SURVIVED,
        f"a break was suggested from origin {cut} of {n}, but the method stays better than the "
        f"baseline after it (error reduction {before:+.3f} before, {after:+.3f} after)",
        original=original,
        attacked=after,
        n_origins=n - cut,
        break_origin_index=where,
        **details,
    )


# --- F6 -----------------------------------------------------------------------


def _f6_outliers(
    test: Backtest, original: float, attacks: AttacksConfig, settings: ForecastConfig
) -> AttackResult:
    lm, lb = _origin_loss(test.model_loss), _origin_loss(test.baseline_loss)
    n = lm.size
    score = np.maximum(_robust_z(lm), _robust_z(lb))
    extreme = np.flatnonzero(score > attacks.outlier_z)
    cap = int(np.floor(attacks.trim_fraction * n))
    drop = extreme[np.argsort(-score[extreme], kind="stable")][:cap]
    if drop.size == 0:
        return _result(
            "F6",
            AttackOutcome.SURVIVED,
            f"no origin has an outlying loss beyond {attacks.outlier_z:g} robust z-scores",
            original=original,
            attacked=original,
            n_origins=n,
        )
    keep = np.ones(n, dtype=bool)
    keep[drop] = False
    if keep.sum() < 2 * settings.attacks.min_origins_per_part:
        return _not_run("F6", "too few origins would be left with the outlying ones removed")
    cleaned = _reduction(lm, lb, keep)
    if cleaned is None:
        return _not_run("F6", "the reduction could not be computed without the outlying origins")
    if cleaned <= 0.0:
        return _result(
            "F6",
            AttackOutcome.BROKEN,
            f"with the {drop.size} origins that have outlying losses removed the method is no "
            f"longer better than the baseline (error reduction {original:+.3f} -> {cleaned:+.3f})",
            original=original,
            attacked=cleaned,
            n_origins=int(keep.sum()),
            removed=int(drop.size),
        )
    return _result(
        "F6",
        AttackOutcome.SURVIVED,
        f"still better than the baseline with the {drop.size} origins that have outlying losses "
        f"removed (error reduction {original:+.3f} -> {cleaned:+.3f})",
        original=original,
        attacked=cleaned,
        n_origins=int(keep.sum()),
        removed=int(drop.size),
    )


def run_forecast_attacks(
    test: Backtest,
    attacks: AttacksConfig,
    settings: ForecastConfig,
) -> list[AttackResult]:
    """Run F1..F6 on the gate's own backtest.

    Guarantees: one result per attack, in F1..F6 order; an attack that raises is recorded as
    NOT_RUN with the error type, never as survived; nothing here reads a p-value or changes a
    verdict -- the caller applies the ratchet.
    """
    original = relative_reduction(test.model_loss, test.baseline_loss)
    steps: list[tuple[str, Callable[[], AttackResult]]] = [
        ("F1", lambda: _f1_leave_out(test, original, attacks)),
        ("F2", lambda: _f2_recent(test, original, settings)),
        ("F3", lambda: _f3_horizons(test, original, settings)),
        ("F4", lambda: _f4_calibration(test, original, settings)),
        ("F5", lambda: _f5_break(test, original, settings)),
        ("F6", lambda: _f6_outliers(test, original, attacks, settings)),
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
