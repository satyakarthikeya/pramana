"""A model's wrong claim must survive transport unchanged and fail real verification."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from pramana.contracts import GateOutcome, Verdict
from pramana.verification.config import load_config
from pramana.verification.gateway import verify_batch
from pramana.verification.memory_guard import writable
from tests.unit.analysis.test_llm_proposer import claim, install_fake_model


def test_wrong_llm_direction_is_refuted_in_one_real_gateway_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pramana.analysis.config import load_config as analysis_config
    from pramana.analysis.hypotheses import llm_proposer
    from pramana.analysis.hypotheses.generation import generate_candidates
    from pramana.analysis.schema_inference import infer_schema
    from tests.fixtures.frames import toy_frame

    monkeypatch.setattr(llm_proposer, "DATA_DIR", tmp_path)
    config = analysis_config()
    hypotheses = config.hypotheses.model_copy(
        update={"proposer": config.hypotheses.proposer.model_copy(update={"engine": "api"})}
    )
    install_fake_model(
        monkeypatch,
        [
            claim(direction="negative"),
            claim(
                claim_type="group_difference",
                variables=["area", "income"],
                reference_group="urban",
            ),
        ],
    )
    frame = toy_frame()
    candidates = generate_candidates(
        frame,
        infer_schema(frame, config.schema_inference),
        hypotheses,
        dataset_ref="toy-llm-test",
        run_id=uuid4(),
    )
    assert len(candidates) == 2
    gateway = load_config()
    gateway = gateway.model_copy(
        update={"statistics": gateway.statistics.model_copy(update={"n_permutations": 1000})}
    )
    proofs = verify_batch(candidates, frame, gateway)
    assert proofs[0].gate_outcome is GateOutcome.REFUTED
    assert proofs[0].verdict is Verdict.REJECT
    assert proofs[1].verdict is Verdict.PASS
    assert len({proof.bh_family_id for proof in proofs}) == 1
    assert writable(proofs) == [proofs[1]]
