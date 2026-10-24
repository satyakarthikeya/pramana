"""S8: the refuter may add checks, never remove one, and fails closed to the defaults."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from pramana.contracts import AttackOutcome, ClaimType, Direction, PermutationScheme
from pramana.contracts import DataStructure
from pramana.verification import gateway
from pramana.verification.attacks import AttackHints, ClaimView, run_attacks
from pramana.verification.gateway import verify_batch
from pramana.verification.refuter import column_profile, suggest_hints
from pramana.verification.schemes import with_period_column
from tests.fixtures.candidates import candidate
from tests.fixtures.config import load_pinned_config

BASE = load_pinned_config()
CLAIM = ClaimView(ClaimType.CORRELATION, "x", "y", PermutationScheme.FREE)


def _confounded(n: int = 300, seed: int = 2) -> pd.DataFrame:
    """x and y are linked only through z; w is unrelated noise."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    return with_period_column(
        pd.DataFrame(
            {
                "x": z + rng.normal(0, 0.6, n),
                "y": z + rng.normal(0, 0.6, n),
                "z": z,
                "w": rng.normal(size=n),
                "region": rng.choice(["n", "s"], n),
            }
        ),
        DataStructure.independent_rows(),
    )


def _config(**attacks):
    return BASE.model_copy(update={"attacks": BASE.attacks.model_copy(update=attacks)})


def _json(**payload) -> str:
    return json.dumps(payload)


def test_the_profile_has_names_and_kinds_but_no_values() -> None:
    profile = column_profile(CLAIM, _confounded(), 10)
    names = {c["name"] for c in profile}
    assert names == {"z", "w", "region"}  # the claim's own variables and the period are left out
    assert all(set(c) == {"name", "kind", "levels"} for c in profile)
    assert "0." not in json.dumps(profile)


def test_empty_garbage_or_failed_suggestions_leave_the_default_checks_untouched() -> None:
    rows = _confounded()
    default = run_attacks(CLAIM, rows, BASE.attacks, seed=1)
    for text in ["", "I cannot help", "[]", _json(controls=[], groups=[]), _json(controls="z")]:
        outcome = suggest_hints(CLAIM, rows, BASE, call=lambda *_: text)
        assert outcome.hints == AttackHints()
        assert run_attacks(CLAIM, rows, BASE.attacks, seed=1, hints=outcome.hints) == default

    def boom(*_):
        raise RuntimeError("no key")

    failed = suggest_hints(CLAIM, rows, BASE, call=boom)
    assert failed.status == "unavailable" and failed.hints == AttackHints()


def test_invented_own_or_non_numeric_columns_are_dropped_and_caps_hold() -> None:
    rows = _confounded()
    text = _json(controls=["nope", "x", "region", "z", "w"], groups=["region", "z", "ghost"])
    outcome = suggest_hints(CLAIM, rows, _config(refuter_max_controls=1), call=lambda *_: text)
    assert outcome.hints.controls == ("z",)  # nope/x/region rejected, w is past the cap of 1
    assert outcome.hints.groups == ("region",)  # z has too many levels to group by, ghost is not a column
    assert any("past the limit" in d for d in outcome.dropped)
    assert any("not a column" in d for d in outcome.dropped)


def test_a_suggested_control_can_only_add_a_check_and_may_break_a_claim() -> None:
    rows = _confounded()
    strict = _config(min_confound_score=0.95).attacks  # the automatic choice finds nothing
    without = {r.attack_id: r for r in run_attacks(CLAIM, rows, strict, seed=1)}
    assert without["A3"].outcome is AttackOutcome.NOT_RUN
    with_hint = {
        r.attack_id: r
        for r in run_attacks(CLAIM, rows, strict, seed=1, hints=AttackHints(controls=("z",)))
    }
    assert with_hint["A3"].outcome is AttackOutcome.BROKEN and with_hint["A3"].details["control"] == "z"
    # every other attack is identical: the hint changed nothing else
    for attack_id in ("A1", "A2", "A5", "A7"):
        assert with_hint[attack_id] == without[attack_id]


def test_a_weaker_suggestion_cannot_hide_a_break_the_automatic_control_finds() -> None:
    rows = _confounded()
    plain = {r.attack_id: r for r in run_attacks(CLAIM, rows, BASE.attacks, seed=1)}
    hinted = {
        r.attack_id: r
        for r in run_attacks(CLAIM, rows, BASE.attacks, seed=1, hints=AttackHints(controls=("w",)))
    }
    assert plain["A3"].outcome is AttackOutcome.BROKEN
    assert hinted["A3"].outcome is AttackOutcome.BROKEN  # still broken: w did not replace z


def _batch(config, rows=None):
    rng = np.random.default_rng(9)
    n = 300
    z = rng.normal(size=n)
    frame = pd.DataFrame({"x": z + rng.normal(0, 0.6, n), "y": z + rng.normal(0, 0.6, n), "z": z})
    claim = candidate("c", "y is positively associated with x", ClaimType.CORRELATION, ["x", "y"],
                      direction=Direction.POSITIVE)
    return verify_batch([claim], frame, config)[0]


def test_the_refuter_is_off_by_default_and_never_called(monkeypatch: pytest.MonkeyPatch) -> None:
    assert BASE.attacks.refuter_enabled is False

    def spy(*_a, **_k):
        raise AssertionError("the refuter must not be called when disabled")

    monkeypatch.setattr(gateway, "suggest_hints", spy)
    _batch(BASE)


def test_enabled_but_unavailable_gives_the_same_proof_as_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a, **_k):
        raise RuntimeError("no key")

    import pramana.verification.refuter as refuter

    monkeypatch.setattr(refuter, "_call_default", boom)
    off = _batch(BASE)
    on = _batch(_config(refuter_enabled=True))
    assert on.model_dump() == off.model_dump()


def test_an_empty_suggestion_list_still_runs_every_applicable_attack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pramana.verification.refuter as refuter

    monkeypatch.setattr(refuter, "_call_default", lambda *_: _json(controls=[], groups=[]))
    off = _batch(BASE)
    on = _batch(_config(refuter_enabled=True))
    assert [a.attack_id for a in on.attacks] == [a.attack_id for a in off.attacks]
    assert [a.outcome for a in on.attacks] == [a.outcome for a in off.attacks]
    assert on.verdict == off.verdict and on.gate_outcome == off.gate_outcome
