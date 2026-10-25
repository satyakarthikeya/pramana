"""S4: the plan is fingerprinted before the rows are read, and a drifted result is refused."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pramana.contracts import ClaimType, Direction, GateOutcome, PermutationScheme
from pramana.contracts.structure import DataStructure
from pramana.verification import gateway
from pramana.verification.executor.runner import ExecutionResult
from pramana.verification.gateway import verify_batch
from pramana.verification.spec import matches, recompute, spec_hash
from tests.fixtures.candidates import candidate
from tests.fixtures.config import load_pinned_config

CONFIG = load_pinned_config()
BASE = dict(
    code="N_PERMUTATIONS = 1000\nSEED = 1\n",
    seed=1,
    n_permutations=1000,
    scheme=PermutationScheme.FREE,
    split_digest="abc",
    direction="positive",
    alpha=0.05,
)


def _frame(n: int = 80, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    return pd.DataFrame({"x": x, "y": x + rng.normal(size=n)})


def _claim():
    return candidate(
        "c",
        "y is positively associated with x",
        ClaimType.CORRELATION,
        ["x", "y"],
        direction=Direction.POSITIVE,
    )


def test_the_hash_is_stable_and_each_plan_field_changes_it() -> None:
    first = spec_hash(**BASE)
    assert first == spec_hash(**BASE)
    for field, other in [
        ("code", BASE["code"] + "# changed\n"),
        ("seed", 2),
        ("n_permutations", 999),
        ("scheme", PermutationScheme.STRATIFIED),
        ("split_digest", "abd"),
        ("direction", "negative"),
        ("alpha", 0.1),
    ]:
        assert spec_hash(**{**BASE, field: other}) != first, field


def test_every_tested_proof_carries_a_hash_that_recomputes_from_its_own_fields() -> None:
    proofs = verify_batch([_claim()], _frame(), CONFIG)
    proof = proofs[0]
    assert proof.spec_hash is not None and len(proof.spec_hash) == 64
    assert matches(proof, CONFIG.statistics.alpha)
    tampered = proof.model_copy(update={"falsification_code": proof.falsification_code + "\n# x"})
    assert not matches(tampered, CONFIG.statistics.alpha)


def test_a_claim_that_was_never_tested_has_no_hash() -> None:
    missing = candidate(
        "m",
        "nope is positively associated with x",
        ClaimType.CORRELATION,
        ["x", "nope"],
        direction=Direction.POSITIVE,
    )
    proof = verify_batch([missing], _frame(), CONFIG)[0]
    assert proof.gate_outcome is GateOutcome.NOT_TESTABLE and proof.spec_hash is None
    assert recompute(proof, 0.05) is None


def test_the_hash_names_the_rows_the_gate_saw() -> None:
    frame = _frame(200)
    from pramana.verification.schemes import split_rows

    structure = DataStructure.independent_rows()
    explore, confirm, record = split_rows(frame, structure, CONFIG)
    a = verify_batch([_claim()], frame.iloc[confirm].reset_index(drop=True), CONFIG, split=record)[
        0
    ]
    b = verify_batch([_claim()], frame.iloc[confirm].reset_index(drop=True), CONFIG)[0]
    assert a.spec_hash != b.spec_hash  # same code and seed, different declared rows


def test_a_result_produced_under_another_seed_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    real = gateway.execute

    def drifted(program, frame, config):
        result = real(program, frame, config)
        payload = dict(result.payload)
        payload["seed"] = int(payload["seed"]) + 1
        return ExecutionResult(**{**result.__dict__, "payload": payload})

    monkeypatch.setattr(gateway, "execute", drifted)
    proof = verify_batch([_claim()], _frame(), CONFIG)[0]
    assert proof.gate_outcome is GateOutcome.INCONCLUSIVE
    assert "frozen plan" in (proof.failure_reason or "")
    assert proof.verdict.value == "REJECT"
