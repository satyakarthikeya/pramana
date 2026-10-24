"""Planted cases for the falsification attacks (PLAN §7.2, §7.3).

Each attack must catch the case it exists for and spare a true effect, and the whole
set together must kill a true moderate finding at most 15% of the time (joint
false-kill). Thresholds come from the shipped config.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.contracts.attack import AttackOutcome
from pramana.contracts.enums import ClaimType, PermutationScheme
from pramana.verification.attacks import ClaimView, run_attacks
from pramana.verification.attacks.runner import PERIOD_COLUMN
from tests.fixtures.config import load_pinned_config


@pytest.fixture(scope="module")
def config():
    return load_pinned_config().attacks


def _corr(x: str = "x", y: str = "y", scheme=PermutationScheme.FREE, entity=None) -> ClaimView:
    return ClaimView(ClaimType.CORRELATION, x, y, scheme, entity_column=entity)


def _by_id(results):
    return {r.attack_id: r for r in results}


def _true_effect(rng: np.random.Generator, n: int = 400) -> pd.DataFrame:
    x = rng.normal(size=n)
    return pd.DataFrame(
        {
            "x": x,
            "y": 0.4 * x + rng.normal(size=n),
            "noise": rng.normal(size=n),
            "site": rng.choice(["a", "b", "c"], size=n),
        }
    )


def test_every_attack_reports_and_none_is_silent(config) -> None:
    results = run_attacks(_corr(), _true_effect(np.random.default_rng(1)), config, seed=1)
    assert [r.attack_id for r in results] == [f"A{i}" for i in range(1, 8)]
    assert all(r.reason for r in results)
    assert all(r.attacked_effect is None for r in results if r.outcome is AttackOutcome.NOT_RUN)


def test_a1_catches_an_effect_made_by_a_few_extreme_points(config) -> None:
    rng = np.random.default_rng(2)
    frame = pd.DataFrame({"x": rng.normal(size=40), "y": rng.normal(size=40)})
    frame.loc[:3, ["x", "y"]] = [[9, 9], [10, 11], [11, 10], [12, 12]]
    assert _by_id(run_attacks(_corr(), frame, config, seed=1))["A1"].outcome is AttackOutcome.BROKEN


def test_a2_catches_an_effect_only_in_the_late_periods(config) -> None:
    rng = np.random.default_rng(3)
    periods = np.repeat(np.arange(40), 20)
    x = rng.normal(size=periods.size)
    late = periods >= 30
    y = np.where(late, 1.5 * x, 0.0) + rng.normal(size=periods.size)
    frame = pd.DataFrame({PERIOD_COLUMN: periods.astype(float), "x": x, "y": y})
    claim = _corr(scheme=PermutationScheme.STRATIFIED)
    assert _by_id(run_attacks(claim, frame, config, seed=1))["A2"].outcome is AttackOutcome.BROKEN


def test_a3_catches_a_confounder_and_spares_an_unrelated_column(config) -> None:
    rng = np.random.default_rng(4)
    z = rng.normal(size=500)
    confounded = pd.DataFrame(
        {"x": z + 0.5 * rng.normal(size=500), "y": z + 0.5 * rng.normal(size=500), "z": z}
    )
    assert (
        _by_id(run_attacks(_corr(), confounded, config, seed=1))["A3"].outcome
        is AttackOutcome.BROKEN
    )
    honest = _by_id(run_attacks(_corr(), _true_effect(rng), config, seed=1))["A3"]
    assert honest.outcome is not AttackOutcome.BROKEN


def test_a4_catches_a_simpson_reversal(config) -> None:
    rng = np.random.default_rng(5)
    parts = []
    for level, offset in (("low", 0.0), ("high", 6.0)):
        x = rng.normal(size=200) + offset
        y = -0.8 * (x - offset) + 2 * offset + 0.5 * rng.normal(size=200)
        parts.append(pd.DataFrame({"x": x, "y": y, "band": level}))
    frame = pd.concat(parts, ignore_index=True)
    assert _by_id(run_attacks(_corr(), frame, config, seed=1))["A4"].outcome is AttackOutcome.BROKEN


def test_a6_catches_a_level_only_association_in_a_panel(config) -> None:
    rng = np.random.default_rng(6)
    rows = []
    for e in range(30):
        level = rng.normal() * 3
        for p in range(10):
            rows.append(
                {
                    "region": f"r{e}",
                    PERIOD_COLUMN: float(p),
                    "x": level + rng.normal(),
                    "y": level + rng.normal(),
                }
            )
    claim = _corr(scheme=PermutationScheme.STRATIFIED, entity="region")
    result = _by_id(run_attacks(claim, pd.DataFrame(rows), config, seed=1))["A6"]
    assert result.outcome is AttackOutcome.BROKEN


def test_a7_catches_an_accounting_identity(config) -> None:
    rng = np.random.default_rng(7)
    revenue = rng.uniform(100, 200, size=300)
    cost = rng.uniform(20, 90, size=300)
    frame = pd.DataFrame({"revenue": revenue, "cost": cost, "net": revenue - cost})
    result = _by_id(run_attacks(_corr("revenue", "net"), frame, config, seed=1))["A7"]
    assert result.outcome is AttackOutcome.BROKEN
    assert "equals" in result.reason


def test_a_trend_runs_its_ordered_attacks(config) -> None:
    rng = np.random.default_rng(8)
    frame = pd.DataFrame(
        {
            PERIOD_COLUMN: np.arange(40.0),
            "month": np.arange(40.0),
            "sales": np.cumsum(1 + rng.normal(size=40)),
        }
    )
    claim = ClaimView(ClaimType.TREND, "month", "sales", PermutationScheme.BLOCK_DIFFERENCED)
    results = _by_id(run_attacks(claim, frame, config, seed=1))
    assert results["A2"].outcome is AttackOutcome.SURVIVED
    assert results["A5"].outcome is AttackOutcome.SURVIVED
    assert results["A3"].outcome is AttackOutcome.NOT_RUN


def test_a_group_difference_with_three_groups_is_unsigned(config) -> None:
    rng = np.random.default_rng(9)
    frame = pd.DataFrame(
        {
            "tier": np.repeat(["a", "b", "c"], 100),
            "spend": np.r_[rng.normal(0, 1, 100), rng.normal(1, 1, 100), rng.normal(2, 1, 100)],
        }
    )
    claim = ClaimView(
        ClaimType.GROUP_DIFFERENCE, "tier", "spend", PermutationScheme.FREE, unsigned=True
    )
    results = _by_id(run_attacks(claim, frame, config, seed=1))
    assert results["A5"].outcome is AttackOutcome.NOT_RUN
    assert results["A1"].outcome is AttackOutcome.SURVIVED


@pytest.mark.slow
@pytest.mark.parametrize("n", [100, 400])
def test_the_whole_attack_set_rarely_kills_a_true_finding(config, n) -> None:
    """At the smallest tables the gate passes as well as at comfortable sizes."""
    trials, killed = 100, 0
    for t in range(trials):
        frame = _true_effect(np.random.default_rng(1000 + t), n=n)
        results = run_attacks(_corr(), frame, config, seed=t)
        killed += any(r.outcome is AttackOutcome.BROKEN for r in results)
    assert killed / trials <= 0.15, f"joint false-kill {killed / trials:.2f} exceeds 0.15"


# --- A2 on evidence (break_rule = interval) ---------------------------------------


def _interval(config):
    return config.model_copy(update={"break_rule": "interval"})


def test_a2_interval_rule_still_catches_an_effect_only_in_the_late_periods(config) -> None:
    rng = np.random.default_rng(3)
    periods = np.repeat(np.arange(40), 20)
    x = rng.normal(size=periods.size)
    y = np.where(periods >= 30, 1.5 * x, 0.0) + rng.normal(size=periods.size)
    frame = pd.DataFrame({PERIOD_COLUMN: periods.astype(float), "x": x, "y": y})
    claim = _corr(scheme=PermutationScheme.STRATIFIED)
    result = _by_id(run_attacks(claim, frame, _interval(config), seed=1))["A2"]
    assert result.outcome is AttackOutcome.BROKEN


def test_a2_interval_rule_does_not_break_a_half_that_is_only_noisy(config) -> None:
    """The point rule kills a true rho 0.25 effect at n = 80 often; the interval rule must not."""
    point_kills = interval_kills = noisy = 0
    for t in range(60):
        rng = np.random.default_rng(500 + t)
        x = rng.normal(size=80)
        frame = pd.DataFrame({"x": x, "y": 0.26 * x + rng.normal(size=80)})
        point = _by_id(run_attacks(_corr(), frame, config, seed=t))["A2"]
        evidence = _by_id(run_attacks(_corr(), frame, _interval(config), seed=t))["A2"]
        point_kills += point.outcome is AttackOutcome.BROKEN
        interval_kills += evidence.outcome is AttackOutcome.BROKEN
        if evidence.outcome is AttackOutcome.NOT_RUN:
            noisy += 1
            assert evidence.applicable and evidence.details["too_noisy"] is True
            assert evidence.attacked_effect is None
    assert interval_kills < point_kills
    assert interval_kills / 60 <= 0.05
    assert noisy > 0  # the third state is reachable: "could not tell" is not "survived"


# --- the ratchet inside the gateway ---------------------------------------------


def test_the_gate_turns_a_confounded_pass_into_fragile() -> None:
    from pramana.contracts.enums import GateOutcome, Verdict
    from pramana.verification.gateway import verify_batch
    from tests.fixtures.candidates import candidate

    shipped = load_pinned_config()
    config = shipped.model_copy(
        update={"statistics": shipped.statistics.model_copy(update={"n_permutations": 999})}
    )
    rng = np.random.default_rng(11)
    z = rng.normal(size=400)
    frame = pd.DataFrame(
        {
            "ice_cream": z + 0.5 * rng.normal(size=400),
            "sunburn": z + 0.5 * rng.normal(size=400),
            "temperature": z,
            "honest_x": (x := rng.normal(size=400)),
            "honest_y": 0.5 * x + rng.normal(size=400),
        }
    )
    claims = [
        candidate(
            "c1",
            "sunburn tends to rise with ice_cream in this data",
            ClaimType.CORRELATION,
            ["ice_cream", "sunburn"],
        ),
        candidate(
            "c2",
            "honest_y tends to rise with honest_x in this data",
            ClaimType.CORRELATION,
            ["honest_x", "honest_y"],
        ),
    ]
    proofs = {p.insight_id: p for p in verify_batch(claims, frame, config)}
    fragile, honest = proofs["c1"], proofs["c2"]
    assert fragile.q_value is not None and fragile.q_value < config.statistics.alpha
    assert fragile.verdict is Verdict.REJECT and fragile.gate_outcome is GateOutcome.FRAGILE
    assert fragile.evidence_score is None
    assert "temperature" in (fragile.failure_reason or "")
    assert honest.verdict is Verdict.PASS and len(honest.attacks) == 7
    assert not any(a.outcome is AttackOutcome.BROKEN for a in honest.attacks)


def test_a3_does_not_control_for_a_near_copy_of_one_side(config) -> None:
    """Partialling out cost (about 0.62 x revenue) would remove revenue itself."""
    rng = np.random.default_rng(12)
    revenue = rng.normal(200, 30, size=400)
    frame = pd.DataFrame(
        {
            "revenue": revenue,
            "cost": 0.62 * revenue + rng.normal(0, 7, size=400),
            "ad_spend": 10 + 0.05 * revenue + rng.normal(0, 3, size=400),
        }
    )
    result = _by_id(run_attacks(_corr("revenue", "ad_spend"), frame, config, seed=1))["A3"]
    assert result.outcome is not AttackOutcome.BROKEN, result.reason
