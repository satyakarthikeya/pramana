"""Both LLM roles use one key; mocked transport still runs real sandbox statistics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pramana.analysis.config import load_config as analysis_config
from pramana.analysis.hypotheses import llm_proposer
from pramana.analysis.schema_inference import infer_schema
from pramana.common import llm_client
from pramana.contracts import Verdict
from pramana.orchestration.adapters import inprocess_verification_adapter
from pramana.orchestration.graph import build_graph, run_graph
from pramana.orchestration.integration import configured_adapters
from pramana.orchestration.state import RunStatus
from pramana.verification.config import load_config as verification_config
from pramana.verification.falsification.generator import generate_from_template
from tests.fixtures.frames import toy_frame
from tests.unit.analysis.test_llm_proposer import claim
from tests.unit.orchestration.helpers import make_run


def test_two_deepseek_roles_execute_real_tests_and_share_run_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRAMANA_ANALYSIS_ENGINE", "api")
    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "llm")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-never-a-live-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-flash")
    monkeypatch.setattr(llm_proposer, "DATA_DIR", tmp_path)
    frame = toy_frame()
    source = tmp_path / "toy.csv"
    frame.to_csv(source, index=False)
    config = analysis_config()
    gateway = verification_config()
    gateway = gateway.model_copy(
        update={
            "statistics": gateway.statistics.model_copy(update={"n_permutations": 199}),
        }
    )
    monkeypatch.setattr("pramana.verification.config.load_config", lambda: gateway)
    candidate = llm_proposer.render_candidate(
        llm_proposer.StructuredClaim.model_validate(claim()),
        frame,
        infer_schema(frame, config.schema_inference),
        config.hypotheses,
        dataset_ref="fixture",
        allowed={"age", "bmi"},
    )
    assert candidate is not None
    source_code = generate_from_template(candidate, gateway).source
    tracing = MagicMock()
    tracing.auth_check.return_value = True
    monkeypatch.setattr(llm_client, "get_langfuse_client", lambda _: tracing)
    monkeypatch.setattr(llm_proposer, "get_langfuse_client", lambda _: tracing)
    calls: list[dict[str, Any]] = []

    def request(settings: llm_client.LLMSettings, payload: bytes) -> dict[str, Any]:
        assert settings.api_key.get_secret_value() == "test-only-never-a-live-key"
        assert settings.base_url == "https://api.deepseek.com"
        sent = json.loads(payload)
        calls.append(sent)
        text = json.dumps({"claims": [claim()]}) if "response_format" in sent else source_code
        return {
            "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {"content": text}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100},
        }

    monkeypatch.setattr(llm_client, "_request", request)
    writes: list[Any] = []

    def write(_state: Any, proofs: list[Any]) -> dict[str, Any]:
        writes.extend(proofs)
        return {"memory_receipts": []}

    state = make_run(str(source))
    final = run_graph(
        state,
        build_graph(
            configured_adapters(
                verify=inprocess_verification_adapter,
                memory_write=write,
                data_dir=tmp_path,
            )
        ),
    )
    assert final.status is RunStatus.COMPLETED
    assert len(calls) == 2
    assert all(item["model"] == "deepseek-flash" for item in calls)
    assert all(item["thinking"] == {"type": "disabled"} for item in calls)
    assert len(final.proof_objects) == 1
    assert final.proof_objects[0].verdict is Verdict.PASS
    assert writes == final.proof_objects
    assert final.proof_objects[0].falsification_code == source_code
    observations = tracing.start_as_current_observation.call_args_list
    assert all(
        call.kwargs["trace_context"]["trace_id"] == state.run_id.hex for call in observations
    )
    assert any(
        call.kwargs.get("metadata", {}).get("insight_id") == candidate.insight_id
        for call in observations
    )
