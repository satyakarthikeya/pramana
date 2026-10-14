"""Measure permutation cost at benchmark scale (docs/OPEN_ISSUES.md item 5).

    PRAMANA_VERIFICATION_GENERATOR=template DEEPSEEK_API_KEY= \
        .venv/Scripts/python.exe scripts/measure_permutation_cost.py

Builds planted datasets at benchmark-like size (rows and column mix from
`configs/evaluation.yaml`), then times the REAL path -- generate + sandboxed `execute`,
with the SHIPPED `n_permutations` and executor timeout -- per claim type. The per-candidate
timeout is what bounds a single execution, so the verdict rests on the SLOWEST claim type,
not the mean, and the extrapolation charges a timed-out candidate its retry.

Nothing here is a threshold: every number comes from the two YAML files.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from itertools import combinations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pramana.contracts.candidate_insight import CandidateInsight  # noqa: E402
from pramana.contracts.enums import ClaimType  # noqa: E402
from pramana.evaluation.config import load_evaluation_config  # noqa: E402
from pramana.evaluation.planted import build_planted_dataset, synthetic_extract  # noqa: E402
from pramana.verification.config import load_config  # noqa: E402
from pramana.verification.executor.runner import execute  # noqa: E402
from pramana.verification.falsification.generator import get_generator  # noqa: E402


def _claim_for(a: str, b: str, kinds: dict[str, str], dataset: str) -> CandidateInsight | None:
    """The claim type a column pair would be tested as, or None if no template fits."""
    pair = {kinds[a], kinds[b]}
    if pair == {"num"}:
        claim_type, variables = ClaimType.CORRELATION, [a, b]
    elif pair == {"ord", "num"}:
        claim_type = ClaimType.TREND
        variables = [a, b] if kinds[a] == "ord" else [b, a]
    elif pair == {"bin", "num"}:
        claim_type = ClaimType.GROUP_DIFFERENCE
        variables = [a, b] if kinds[a] == "bin" else [b, a]
    else:
        return None
    return CandidateInsight(
        insight_id=f"{variables[0]}__{variables[1]}",
        claim=f"{variables[0]} is associated with {variables[1]}",
        claim_type=claim_type,
        variables=variables,
        dataset_ref=dataset,
    )


def main() -> None:
    evaluation = load_evaluation_config()
    config = load_config()  # shipped config; generator pinned by PRAMANA_VERIFICATION_GENERATOR
    if config.llm.generator != "template":
        raise SystemExit("set PRAMANA_VERIFICATION_GENERATOR=template (no API calls here)")
    shape = evaluation.extract_shape
    frame, ordinal = synthetic_extract(shape, seed=evaluation.planted.base_seed)
    dataset = build_planted_dataset(
        frame, dataset_id="cost-0", dataset_index=0, config=evaluation,
        verification=config, ordinal_columns=ordinal,
    )
    kinds = {c: c.split("_")[0] for c in dataset.frame.columns}
    claims = [
        claim
        for a, b in combinations(dataset.frame.columns, 2)
        if (claim := _claim_for(a, b, kinds, "cost-0")) is not None
    ]
    n_pairs_total = len(list(combinations(dataset.frame.columns, 2)))
    generate = get_generator(config)
    per_type: dict[str, list[float]] = {}
    take = evaluation.measurement.candidates_timed_per_claim_type
    counts: dict[str, int] = {}
    for claim in claims:
        counts[claim.claim_type.value] = counts.get(claim.claim_type.value, 0) + 1
    for claim_type in ClaimType:
        sample = [c for c in claims if c.claim_type is claim_type][:take]
        for claim in sample:
            started = time.perf_counter()
            result = execute(generate(claim, config), dataset.frame, config)
            elapsed = time.perf_counter() - started
            if not result.ok:
                print(f"  FAILED {claim.insight_id}: {result.failure_reason}", file=sys.stderr)
            per_type.setdefault(claim_type.value, []).append(elapsed)

    timeout = config.executor.timeout_seconds
    attempts = config.executor.max_retries + 1
    n_datasets = evaluation.measurement.benchmark_datasets
    rows = []
    dataset_seconds = 0.0
    for claim_type, times in per_type.items():
        rows.append(
            {
                "claim_type": claim_type,
                "n_timed": len(times),
                "mean_s": statistics.mean(times),
                "max_s": max(times),
                "candidates_per_dataset": counts[claim_type],
            }
        )
        dataset_seconds += statistics.mean(times) * counts[claim_type]
    slowest = max(row["max_s"] for row in rows)
    summary = {
        "n_rows": shape.n_rows,
        "n_columns": len(dataset.frame.columns),
        "n_pairs_total": n_pairs_total,
        "n_testable_candidates": len(claims),
        "n_permutations": config.statistics.n_permutations,
        "timeout_seconds": timeout,
        "per_claim_type": rows,
        "seconds_per_dataset_all_candidates": dataset_seconds,
        "benchmark_datasets": n_datasets,
        "total_hours_all_candidates": dataset_seconds * n_datasets / 3600.0,
        "slowest_single_candidate_s": slowest,
        "timeout_headroom_x": timeout / slowest,
        "worst_case_all_timeout_hours": len(claims) * n_datasets * timeout * attempts / 3600.0,
        "timeout_safe": slowest < timeout,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
