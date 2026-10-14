"""The per-run log: enough to re-derive every number in the results table without re-running.

SPEC.md 5 requires, per run: dataset id and build seed, the injected truth table, the
condition, model and generator, a snapshot of the gateway config (alpha, `n_permutations`,
seed, thresholds) and every proof object, with `bh_family_id` tying each verdict to its
family. The log also carries the candidates and the reported ids, because condition A has
no proof objects and its reported set would otherwise not be recomputable.

For condition A the gate fields (`generator`, `proofs`, `bh_family_id`) are explicit
nulls, not missing keys: a reader can tell "no gate was run" from "the field was lost".

The file is written with sorted keys and a fixed indent, so the same run produces the
same bytes. `emit` writes one structured JSON line per event carrying `insight_id`
where one applies (AGENTS.md 5).

Owner: P.P. Satya Karthikeya
Scope: src/pramana/evaluation/SPEC.md 5
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.evaluation.conditions import Condition, ConditionResult
from pramana.evaluation.metrics import DatasetScore, score_reported
from pramana.evaluation.planted import GroundTruth
from pramana.verification.config import VerificationConfig

_log = logging.getLogger(__name__)

#: Top-level keys SPEC.md 5 requires. Tests assert each is present for every condition.
SPEC_SECTION_5_FIELDS: tuple[str, ...] = (
    "dataset_id",
    "build_seed",
    "truth",
    "condition",
    "model",
    "generator",
    "gateway_config",
    "proofs",
    "bh_family_id",
)


class GatewayConfigSnapshot(BaseModel):
    """The gateway settings the run used, copied at run time (the YAML may change later)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    alpha: float
    n_permutations: int
    n_bootstrap: int
    seed: int
    min_observations: int
    effect_thresholds: dict[str, dict[str, float]]
    timeout_seconds: int
    generator: str


class RunLog(BaseModel):
    """One condition's run on one dataset."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str
    build_seed: int
    truth: GroundTruth
    condition: str
    model: str
    generator: str | None
    gateway_config: GatewayConfigSnapshot
    candidates: list[CandidateInsight]
    reported_ids: list[str]
    proofs: list[dict[str, Any]] | None
    bh_family_id: str | None


def snapshot_gateway_config(config: VerificationConfig) -> GatewayConfigSnapshot:
    """Copy the values that decide a verdict out of the live config."""
    return GatewayConfigSnapshot(
        alpha=config.statistics.alpha,
        n_permutations=config.statistics.n_permutations,
        n_bootstrap=config.statistics.n_bootstrap,
        seed=config.statistics.seed,
        min_observations=config.statistics.min_observations,
        effect_thresholds={
            metric.value: {"min": band.min, "strong": band.strong}
            for metric, band in sorted(
                config.evidence.effect_thresholds.items(), key=lambda item: item[0].value
            )
        },
        timeout_seconds=config.executor.timeout_seconds,
        generator=config.llm.generator,
    )


def build_run_log(
    truth: GroundTruth, result: ConditionResult, verification: VerificationConfig
) -> RunLog:
    """Assemble the log of one condition run from its truth, result and live gateway config."""
    return RunLog(
        dataset_id=truth.dataset_id,
        build_seed=truth.build_seed,
        truth=truth,
        condition=Condition(result.condition).value,
        model=result.model,
        generator=result.generator,
        gateway_config=snapshot_gateway_config(verification),
        candidates=result.candidates,
        reported_ids=result.reported_ids,
        proofs=(
            None
            if result.proofs is None
            else [json.loads(proof.model_dump_json()) for proof in result.proofs]
        ),
        bh_family_id=result.bh_family_id,
    )


def write_run_log(log: RunLog, path: Path | str) -> Path:
    """Write `log` as deterministic JSON (sorted keys) and return the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(log.model_dump_json())
    target.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return target


def read_run_log(path: Path | str) -> RunLog:
    """Read a log written by `write_run_log`."""
    return RunLog.model_validate_json(Path(path).read_text(encoding="utf-8"))


def score_run_log(log: RunLog) -> DatasetScore:
    """Recompute the dataset's score from the log alone: no re-run, no live objects."""
    reported = set(log.reported_ids)
    return score_reported(log.truth, [c for c in log.candidates if c.insight_id in reported])


def emit(event: str, *, insight_id: str | None = None, **fields: Any) -> None:
    """One structured JSON log line; carries `insight_id` when the event concerns a claim."""
    record: dict[str, Any] = {"event": event, **fields}
    if insight_id is not None:
        record["insight_id"] = insight_id
    _log.info(json.dumps(record, sort_keys=True))
