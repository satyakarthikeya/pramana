from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
import pytest

from pramana.orchestration import tasks
from tests.unit.orchestration.helpers import candidate, proof


def test_native_handler_refuses_a_dataset_outside_the_run_artifact_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks, "_handler", None)
    monkeypatch.delenv("PRAMANA_VERIFICATION_HANDLER", raising=False)
    with pytest.raises(ValueError, match="cleaned artifact"):
        tasks.native_verification_handler(
            {
                "run_id": "00000000-0000-0000-0000-000000000001",
                "candidate_insights": [],
                "dataset_ref": "toy.pkl",
            }
        )


def test_task_requires_proof_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "_handler", lambda _request: {})
    with pytest.raises(ValueError, match="proof_objects"):
        tasks.verify_batch_task.run("run-1", [], "toy")


def test_task_passes_whole_family_to_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def handler(request: dict[str, Any]) -> dict[str, Any]:
        seen.update(request)
        return {
            "proof_objects": [
                proof(item["insight_id"], passed=False)
                for item in request["candidate_insights"]
            ]
        }

    monkeypatch.setattr(tasks, "_handler", handler)
    candidates = [candidate("a"), candidate("b")]
    result = tasks.verify_batch_task.run(
        "run-1",
        [item.model_dump(mode="json") for item in candidates],
        "toy.csv",
    )
    assert [item["insight_id"] for item in seen["candidate_insights"]] == ["a", "b"]
    assert [item["insight_id"] for item in result["proof_objects"]] == ["a", "b"]


def test_task_validates_and_serializes_proof_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tasks,
        "_handler",
        lambda _request: {"proof_objects": [proof("finding", passed=True)]},
    )
    item = candidate("finding")
    result = tasks.verify_batch_task.run("run-1", [item.model_dump(mode="json")], "toy.csv")
    assert result["proof_objects"][0]["insight_id"] == "finding"
    assert result["proof_objects"][0]["verdict"] == "PASS"


def test_task_rejects_missing_or_reordered_proofs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tasks,
        "_handler",
        lambda _request: {"proof_objects": [proof("b", passed=False)]},
    )
    items = [candidate("a"), candidate("b")]
    with pytest.raises(ValueError, match="exactly one proof per candidate"):
        tasks.verify_batch_task.run(
            "run-1",
            [item.model_dump(mode="json") for item in items],
            "toy.csv",
        )


def test_native_handler_loads_the_exact_cleaned_frame(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = UUID("00000000-0000-0000-0000-000000000001")
    cleaned_path = tmp_path / "runs" / str(run_id) / "cleaned.pkl"
    cleaned_path.parent.mkdir(parents=True)
    expected_frame = pd.DataFrame({"x": range(40), "y": range(40)})
    expected_frame.to_pickle(cleaned_path)
    item = candidate("finding").model_copy(update={"dataset_ref": str(cleaned_path)})
    captured: dict[str, Any] = {}

    def fake_verify(candidates: list[Any], frame: pd.DataFrame, _config: Any) -> list[Any]:
        captured["candidates"] = candidates
        captured["frame"] = frame
        return [proof("finding", passed=False)]

    monkeypatch.setattr("pramana.verification.gateway.verify_batch", fake_verify)
    result = tasks.native_verification_handler(
        {
            "run_id": str(run_id),
            "candidate_insights": [item.model_dump(mode="json")],
            "dataset_ref": str(cleaned_path),
        },
        data_dir=tmp_path,
    )

    assert [candidate.insight_id for candidate in captured["candidates"]] == ["finding"]
    pd.testing.assert_frame_equal(captured["frame"], expected_frame)
    assert result["proof_objects"][0].insight_id == "finding"


def test_task_relies_on_graph_retry_instead_of_late_acknowledgement() -> None:
    assert tasks.verify_batch_task.acks_late is False


def test_worker_timeout_covers_executor_timeout() -> None:
    tasks.validate_worker_timeouts()


def test_worker_refuses_soft_limit_that_cannot_cover_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pramana.verification.config import load_config as load_verification_config

    executor_timeout = load_verification_config().executor.timeout_seconds
    bad_queue = tasks._runtime.queue.model_copy(
        update={
            "task_soft_time_limit": executor_timeout,
            "task_hard_time_limit": executor_timeout + 5,
            "result_timeout_seconds": executor_timeout + 10,
        }
    )
    monkeypatch.setattr(tasks, "_runtime", tasks._runtime.model_copy(update={"queue": bad_queue}))
    with pytest.raises(RuntimeError, match="must exceed"):
        tasks.validate_worker_timeouts()


def test_worker_logging_uses_runtime_level(monkeypatch: pytest.MonkeyPatch) -> None:
    levels: list[str] = []
    monkeypatch.setattr(tasks, "configure_logging", levels.append)
    tasks.configure_worker_logging()
    assert levels == [tasks._runtime.logging.level]
