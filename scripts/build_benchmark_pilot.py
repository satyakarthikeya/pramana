"""Build or check a ten- or forty-extract handoff. Never shuffle or inject."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pramana.analysis.benchmark.curation import (  # noqa: E402
    DEFAULT_PLAN,
    build_extract,
    load_extract,
    load_plan,
    prepare_sources,
    schema_for_extract,
    sha256,
    write_json,
)
from pramana.analysis.config import load_config  # noqa: E402
from pramana.analysis.hypotheses.generation import generate_candidates  # noqa: E402


def main() -> int:
    """Validate every planned handoff and publish aggregate audit metadata only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--metadata-report", type=Path)
    parser.add_argument("--source-lock", type=Path)
    args = parser.parse_args()
    plan = load_plan(args.plan)
    if args.source_lock is None:
        args.source_lock = args.plan.with_name(f"{args.plan.stem}_sources.json")
    raw = args.data_dir / "raw/nhanes"
    output = args.data_dir / "benchmark/extracts"
    if not args.offline and not args.check_only:
        prepare_sources(plan, raw)
    if args.source_lock.is_file() and not args.check_only:
        lock = json.loads(args.source_lock.read_text("utf-8"))
        for name, expected in lock["sha256"].items():
            if sha256(raw / name) != expected:
                raise ValueError(f"source changed from the reviewed lock: {name}")
    results = []
    metadata_reports = []
    people: dict[str, set[tuple[float, float]]] = {}
    source_hashes: dict[str, str] = {}
    config = load_config()
    for spec in plan.extracts:
        if not args.check_only:
            build_extract(spec, plan, raw, output)
        frame, metadata = load_extract(output / spec.dataset_id)
        metadata_reports.append(metadata.model_dump(mode="json"))
        if metadata.row_count != len(spec.cycles) * spec.rows_per_cycle:
            raise ValueError(f"unexpected row count: {spec.dataset_id}")
        schema = schema_for_extract(frame, metadata)
        candidates = generate_candidates(
            frame,
            schema,
            config.hypotheses,
            dataset_ref=str((output / spec.dataset_id / "extract.csv").resolve()),
        )
        kinds = {
            kind: sum(item.claim_type.value == kind for item in candidates)
            for kind in ("correlation", "group_difference", "trend")
        }
        # Do not select/alter real data to force a native association. Satya supplies injections.
        axis = spec.time_column
        if spec.coverage == "trends" and (
            axis is None or not schema.columns[axis].is_time_like or frame[axis].nunique() < 2
        ):
            raise ValueError(f"missing ordered cycle axis: {spec.dataset_id}")
        people[spec.dataset_id] = set(
            frame[["SDDSRVYR", "SEQN"]].itertuples(index=False, name=None)
        )
        for record in metadata.sources:
            source_hashes[f"{record.component}.xpt"] = record.data_sha256
            source_hashes[f"{record.component}.htm"] = record.codebook_sha256
        results.append(
            {
                "dataset_id": spec.dataset_id,
                "cycle": metadata.cycle,
                "row_count": metadata.row_count,
                "column_count": metadata.column_count,
                "coverage": metadata.coverage,
                "time_column": metadata.time_column,
                "extract_sha256": metadata.extract_sha256,
                "cohort_sha256": metadata.cohort_sha256,
                "duplicates_removed": metadata.duplicates_removed,
                "nonresponse_replaced": sum(
                    item.nonresponse_replaced for item in metadata.columns.values()
                ),
                "missing_cells": sum(item.missing_count for item in metadata.columns.values()),
                "candidate_counts_unverified": kinds,
                "relative_path": f"data/benchmark/extracts/{spec.dataset_id}",
            }
        )
        print(
            f"{spec.dataset_id}: {len(frame)} rows, {len(frame.columns)} columns; handoff valid",
            flush=True,
        )
    summary = {
        "phase": (
            "approved_pilot_10" if plan.phase == "pilot" else "benchmark_40_awaiting_evaluation"
        ),
        "approval": (
            "Satya approval relayed by Rohith, 2026-10-18"
            if plan.phase == "pilot"
            else "Rohith authorized expansion 2026-10-18; Satya pilot evaluation pending"
        ),
        "plan_sha256": hashlib.sha256(
            json.dumps(plan.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "sampling_seed": plan.seed,
        "pandas_version": metadata.pandas_version,
        "datasets": results,
        "participant_overlap_counts": {
            left: {right: len(ids & other) for right, other in people.items()}
            for left, ids in people.items()
        },
        "limits": [
            "Source handoffs only; Satya's injection and evaluation have not been run",
            "Extracts overlap participants; do not treat them as independent population samples",
            "Candidate counts are unverified proposals, not findings or evaluation results",
            "No column shuffle, injection, truth labels or verdicts produced by this builder",
        ],
    }
    if args.summary:
        write_json(args.summary, summary)
    if args.metadata_report:
        write_json(
            args.metadata_report, {"phase": summary["phase"], "datasets": metadata_reports}
        )
    if not args.source_lock.is_file() and not args.check_only:
        write_json(
            args.source_lock,
            {
                "source": "Official CDC NHANES public-use files",
                "sha256": dict(sorted(source_hashes.items())),
            },
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
