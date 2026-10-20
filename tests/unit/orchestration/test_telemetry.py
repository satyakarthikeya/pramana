"""Worker result telemetry is bounded and never changes execution or proofs."""

from contextlib import contextmanager
from typing import Any
from uuid import uuid4

from pramana.orchestration.telemetry import relay_verification_result
from tests.unit.orchestration.helpers import batch_summary, proof


def test_relay_uses_run_trace_and_bounds_metadata_without_error_source() -> None:
    seen: list[dict[str, Any]] = []

    class Client:
        @contextmanager
        def start_as_current_observation(self, **values: Any) -> Any:
            seen.append(values)
            yield None

    proofs = [proof("x" * 200 + str(i), passed=False) for i in range(60)]
    run_id = uuid4()
    assert relay_verification_result(Client(), run_id, batch_summary(60), proofs)
    assert seen[0]["trace_context"] == {"trace_id": run_id.hex}
    metadata = seen[0]["metadata"]
    assert len(metadata["insights"]) == 50
    assert metadata["truncated_insight_count"] == 10
    assert all(len(row["insight_id"]) <= 128 for row in metadata["insights"])
    assert "falsification_code" not in str(metadata)
    assert "failure_reason" not in str(metadata)


def test_unavailable_or_broken_tracing_is_not_an_execution_failure() -> None:
    assert not relay_verification_result(None, uuid4(), batch_summary(0), [])

    class Broken:
        def start_as_current_observation(self, **_values: Any) -> Any:
            raise RuntimeError("secret trace exception must not escape")

    assert not relay_verification_result(Broken(), uuid4(), batch_summary(0), [])
