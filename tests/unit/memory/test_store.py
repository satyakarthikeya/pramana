"""The memory write path: every write goes through the guard, all-or-nothing."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from pramana.contracts import EffectMetric, GateOutcome, ProofObject, ScoreComponents, Verdict
from pramana.contracts import TestType as ProofTestType
from pramana.memory.store import STORE_PATH_ENV, read_records, write_proofs, write_verified
from pramana.verification.memory_guard import MemoryWriteRefused


def _proof(insight_id: str, outcome: GateOutcome) -> ProofObject:
    supported = outcome is GateOutcome.SUPPORTED
    return ProofObject(
        insight_id=insight_id,
        verdict=Verdict.PASS if supported else Verdict.REJECT,
        p_value=0.001,
        q_value=0.004,
        effect_size=0.42,
        evidence_score=0.6 if supported else None,
        score_components=ScoreComponents(s_q=0.6, s_e=0.6, s_r=1.0) if supported else None,
        test_type=ProofTestType.PERMUTATION,
        falsification_code="# generated",
        n_hypotheses_in_batch=2,
        gate_outcome=outcome,
        effect_metric=EffectMetric.SPEARMAN_RHO,
        bh_family_id="bh-test",
        seed=1,
    )


def test_a_passed_proof_is_stored_with_its_full_proof(tmp_path: Path) -> None:
    store = tmp_path / "memory.jsonl"
    proof = _proof("ok", GateOutcome.SUPPORTED)

    written = write_proofs([proof], run_id="run-1", dataset_ref="d#c", path=store)
    stored = read_records(store)

    assert stored == written
    assert stored[0].insight_id == "ok"
    assert stored[0].verdict is Verdict.PASS
    assert ProofObject.model_validate(stored[0].proof) == proof


@pytest.mark.parametrize(
    "outcome", [GateOutcome.REFUTED, GateOutcome.NEGLIGIBLE, GateOutcome.INCONCLUSIVE]
)
def test_one_rejected_proof_refuses_the_whole_batch(tmp_path: Path, outcome: GateOutcome) -> None:
    store = tmp_path / "memory.jsonl"
    batch = [_proof("ok", GateOutcome.SUPPORTED), _proof("bad", outcome)]

    with pytest.raises(MemoryWriteRefused):
        write_proofs(batch, run_id="run-1", dataset_ref=None, path=store)
    assert read_records(store) == []


def test_the_handler_accepts_orchestrations_request_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "memory.jsonl"
    monkeypatch.setenv(STORE_PATH_ENV, str(store))
    proof = _proof("ok", GateOutcome.SUPPORTED)
    run_id = uuid4()

    result = write_verified(
        {"run_id": run_id, "dataset_ref": "d#c", "proof_objects": [proof.model_dump()]}
    )

    receipts = result["memory_receipts"]
    assert [receipt["insight_id"] for receipt in receipts] == ["ok"]
    assert read_records(store)[0].run_id == str(run_id)


def test_the_handler_guards_even_if_orchestration_did_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = tmp_path / "memory.jsonl"
    monkeypatch.setenv(STORE_PATH_ENV, str(store))
    rejected = _proof("bad", GateOutcome.INCONCLUSIVE).model_dump()

    with pytest.raises(MemoryWriteRefused):
        write_verified({"run_id": uuid4(), "dataset_ref": None, "proof_objects": [rejected]})
    assert not store.exists()


def test_no_module_outside_memory_imports_chromadb() -> None:
    root = Path(__file__).resolve().parents[3] / "src" / "pramana"
    offenders = [
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if "memory" not in path.relative_to(root).parts[:1]
        and any(
            line.strip().startswith(("import chromadb", "from chromadb"))
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    ]
    assert offenders == []
