from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from pramana.contracts import ProofObject, Verdict
from pramana.orchestration.graph import build_graph, run_graph
from pramana.orchestration.integration import configured_adapters
from pramana.orchestration.state import PramanaState, RunStatus
from pramana.orchestration.tasks import native_verification_handler
from tests.fixtures.frames import toy_frame
from tests.unit.orchestration.helpers import make_run


def test_real_analysis_family_runs_through_gateway_and_pass_only_memory_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "PRAMANA_INGEST_HANDLER",
        "PRAMANA_PREPARATION_HANDLER",
        "PRAMANA_ANALYSIS_HANDLER",
    ):
        monkeypatch.delenv(name, raising=False)

    source = tmp_path / "toy.csv"
    toy_frame().to_csv(source, index=False)
    memory_seen: list[ProofObject] = []

    def verify(state: PramanaState) -> dict[str, Any]:
        return dict(
            native_verification_handler(
                {
                    "run_id": str(state.run_id),
                    "candidate_insights": [
                        candidate.model_dump(mode="json") for candidate in state.candidate_insights
                    ],
                    "dataset_ref": state.dataset_ref,
                },
                data_dir=tmp_path,
            )
        )

    def memory_write(_state: PramanaState, proofs: Sequence[ProofObject]) -> dict[str, Any]:
        memory_seen.extend(proofs)
        return {
            "memory_receipts": [
                {"insight_id": proof.insight_id, "stored": True} for proof in proofs
            ]
        }

    adapters = configured_adapters(
        verify=verify,
        memory_write=memory_write,
        data_dir=tmp_path,
    )
    final = run_graph(make_run(str(source)), build_graph(adapters))

    assert final.status is RunStatus.COMPLETED
    assert final.candidate_insights
    assert [proof.insight_id for proof in final.proof_objects] == [
        candidate.insight_id for candidate in final.candidate_insights
    ]
    assert all(proof.verdict is Verdict.PASS for proof in memory_seen)
    rejected_ids = {
        proof.insight_id for proof in final.proof_objects if proof.verdict is Verdict.REJECT
    }
    assert rejected_ids.isdisjoint({proof.insight_id for proof in memory_seen})
    assert final.report is not None
    assert all(row["proof"].verdict is Verdict.PASS for row in final.report["insights"])
