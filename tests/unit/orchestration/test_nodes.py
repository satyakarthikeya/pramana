from typing import Any

import pytest

from pramana.orchestration.nodes.memory_node import memory_node
from pramana.orchestration.nodes.report_node import report_node
from pramana.orchestration.nodes.verification_node import verification_node
from tests.unit.orchestration.helpers import candidate, make_run, proof


def test_memory_node_forwards_only_explicit_pass() -> None:
    state = make_run()
    state.proof_objects = [proof("pass", passed=True), proof("reject", passed=False)]
    received: list[Any] = []

    def memory_adapter(_state: Any, proofs: Any) -> dict[str, Any]:
        received.extend(proofs)
        return {"memory_receipts": ["stored"]}

    memory_node(state, memory_adapter)
    assert [item.insight_id for item in received] == ["pass"]


def test_verification_node_rejects_duplicate_candidate_ids_before_dispatch() -> None:
    state = make_run()
    state.candidate_insights = [candidate("duplicate"), candidate("duplicate")]
    called = False

    def verify_adapter(_state: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {"proof_objects": []}

    with pytest.raises(ValueError, match="unique"):
        verification_node(state, verify_adapter)
    assert called is False


def test_report_node_rejects_an_unverified_insight() -> None:
    state = make_run()

    def unsafe_report(_state: Any) -> dict[str, Any]:
        return {"report": {"insights": [{"claim": "unsafe"}]}}

    with pytest.raises(ValueError, match="PASS proof"):
        report_node(state, unsafe_report)


def test_report_node_rejects_malformed_report_shape() -> None:
    state = make_run()

    with pytest.raises(ValueError, match="mapping"):
        report_node(state, lambda _state: {"report": "unsafe"})


def test_report_node_rejects_a_rejected_proof() -> None:
    state = make_run()

    def unsafe_report(_state: Any) -> dict[str, Any]:
        return {"report": {"insights": [{"claim": "unsafe", "proof": {"verdict": "REJECT"}}]}}

    with pytest.raises(ValueError, match="PASS proof"):
        report_node(state, unsafe_report)


def test_report_node_rejects_forged_pass_not_issued_by_gateway() -> None:
    state = make_run()

    def forged_report(_state: Any) -> dict[str, Any]:
        return {
            "report": {
                "insights": [{"claim": "forged", "proof": {"insight_id": "x", "verdict": "PASS"}}]
            }
        }

    with pytest.raises(ValueError, match="gateway-issued PASS"):
        report_node(state, forged_report)


def test_report_node_accepts_original_claim_with_exact_pass_proof() -> None:
    state = make_run()
    original = candidate("x")
    issued = proof("x", passed=True)
    state.candidate_insights = [original]
    state.proof_objects = [issued]

    def safe_report(_state: Any) -> dict[str, Any]:
        return {
            "report": {
                "insights": [
                    {
                        "insight_id": "x",
                        "claim": original.claim,
                        "proof": issued,
                    }
                ]
            }
        }

    assert report_node(state, safe_report)["report"]["insights"][0]["proof"] is issued


def test_report_node_rejects_mismatched_report_insight_id() -> None:
    state = make_run()
    original = candidate("x")
    issued = proof("x", passed=True)
    state.candidate_insights = [original]
    state.proof_objects = [issued]

    def mismatched_report(_state: Any) -> dict[str, Any]:
        return {
            "report": {
                "insights": [
                    {
                        "insight_id": "different",
                        "claim": original.claim,
                        "proof": issued,
                    }
                ]
            }
        }

    with pytest.raises(ValueError, match="exact gateway-issued"):
        report_node(state, mismatched_report)
