"""The sentences for a claim that passed and one an attack broke (wording only).

Known-answer cases built from hand-made proofs: the wording never decides a verdict, so these
check that the counts K of M, "could not tell" and the limits are always stated, and that a
break is described as not being proof the claim is false.
"""

from __future__ import annotations

from pramana.api.v1 import rejection_reason
from pramana.contracts import AttackOutcome, AttackResult, GateOutcome, ProofObject
from tests.unit.memory.test_store import _proof as _stored_proof


def _attack(attack_id: str, outcome: AttackOutcome, *, applicable: bool = True) -> AttackResult:
    return AttackResult(
        attack_id=attack_id,
        name=f"check {attack_id}",
        outcome=outcome,
        reason="the effect shrinks in the later half",
        applicable=applicable,
    )


def _proof(gate: GateOutcome, attacks: list[AttackResult]) -> ProofObject:
    return _stored_proof("w", gate).model_copy(update={"attacks": attacks})


S, B, N = AttackOutcome.SURVIVED, AttackOutcome.BROKEN, AttackOutcome.NOT_RUN


def test_held_up_states_k_of_m_and_what_could_not_tell() -> None:
    attacks = [
        _attack("A1", S),
        _attack("A2", S),
        _attack("A3", S),
        _attack("A4", N),
        _attack("A5", S),
        _attack("A6", N, applicable=False),
    ]
    text = rejection_reason(_proof(GateOutcome.SUPPORTED, attacks))
    assert text.startswith("Held up:")
    assert "survived 4 of 4 further checks that could be run" in text
    assert "(1 applicable check could not tell)" in text  # the not-applicable one is not counted
    assert "columns in this table only" in text and "not a causal conclusion" in text


def test_a_pass_with_one_check_run_is_labelled_little_checked_not_held_up() -> None:
    text = rejection_reason(_proof(GateOutcome.SUPPORTED, [_attack("A1", S), _attack("A2", N)]))
    assert text.startswith("Passed the significance test") and "little was checked" in text
    assert "survived 1 of 1 further checks" in text and "Held up" not in text


def test_a_pass_with_nothing_run_says_so_instead_of_claiming_checks() -> None:
    text = rejection_reason(_proof(GateOutcome.SUPPORTED, []))
    assert "little was checked: no further check could be run" in text
    assert "survived" not in text


def test_fragile_names_the_check_and_says_a_break_is_not_proof_of_falsity() -> None:
    attacks = [_attack("A1", S), _attack("A2", B), _attack("A3", S)]
    text = rejection_reason(_proof(GateOutcome.FRAGILE, attacks))
    assert "the check a2 check broke it" in text  # the name is lower-cased inside the sentence
    assert "2 of 3 further checks that could be run survived" in text
    assert "not proof the claim is false" in text
