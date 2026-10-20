"""Prepared code remains bound to its data/config and failures stay fail-closed."""

from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import pytest

from pramana.orchestration.tasks import native_verification_handler
from pramana.orchestration.verification_integration import (
    prepare_verification,
    prepared_generator,
)
from pramana.verification.config import load_config
from pramana.verification.falsification.generator import GeneratorError, generate_from_template
from tests.unit.orchestration.helpers import candidate


def test_prepared_program_is_bound_to_exact_candidates_and_configuration() -> None:
    config = load_config()
    item = candidate("a")
    frame = pd.DataFrame({"x": range(40), "y": range(40)})
    batch = prepare_verification([item], frame, config)
    generate = prepared_generator(batch, [item], config)
    assert generate(item, config).source == generate_from_template(item, config).source
    changed = config.model_copy(
        update={
            "statistics": config.statistics.model_copy(update={"seed": config.statistics.seed + 1})
        }
    )
    with pytest.raises(ValueError, match="configurations differ"):
        prepared_generator(batch, [item], changed)
    with pytest.raises(ValueError, match="exact candidate family"):
        prepared_generator(batch, [item.model_copy(update={"claim": "a different claim"})], config)


def test_failed_generation_is_retained_without_template_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config()

    def fail(*_args: Any) -> Any:
        raise GeneratorError("Provider unavailable")

    monkeypatch.setattr(
        "pramana.orchestration.verification_integration.get_generator", lambda _: fail
    )
    item = candidate("a")
    batch = prepare_verification([item], pd.DataFrame({"x": [1], "y": [2]}), config)
    with pytest.raises(GeneratorError, match="Provider unavailable"):
        prepared_generator(batch, [item], config)(item, config)


def test_worker_runs_prepared_source_without_calling_the_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config()
    config = config.model_copy(
        update={
            "llm": config.llm.model_copy(update={"generator": "llm"}),
            "statistics": config.statistics.model_copy(update={"n_permutations": 199}),
        }
    )
    run_id = uuid4()
    path = tmp_path / "runs" / str(run_id) / "cleaned.pkl"
    path.parent.mkdir(parents=True)
    frame = pd.DataFrame({"x": range(40), "y": range(40)})
    frame.to_pickle(path)
    item = candidate("a").model_copy(update={"dataset_ref": str(path)})

    def generated(c: Any, cfg: Any) -> Any:
        # An explicitly injected fixture models code returned by the trusted process.
        return generate_from_template(c, cfg).model_copy(update={"generator": "llm"})

    monkeypatch.setattr(
        "pramana.orchestration.verification_integration.get_generator", lambda _: generated
    )
    batch = prepare_verification([item], frame, config)
    monkeypatch.setattr("pramana.verification.config.load_config", lambda: config)
    monkeypatch.setattr(
        "pramana.verification.gateway.get_generator",
        lambda _: pytest.fail("An isolated worker must not call the LLM"),
    )
    request = {
        "run_id": str(run_id),
        "dataset_ref": str(path),
        "candidate_insights": [item.model_dump(mode="json")],
        "generated_batch": batch.model_dump(mode="json"),
    }
    result = native_verification_handler(request, data_dir=tmp_path)
    assert result["proof_objects"][0].verdict.value == "PASS"
    del request["generated_batch"]
    with pytest.raises(ValueError, match="trusted process"):
        native_verification_handler(request, data_dir=tmp_path)
