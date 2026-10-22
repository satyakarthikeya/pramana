"""Audit existing local runs without new model calls; optionally add one mixed-type run.

Replays stored source in the real sandbox only: no new BH verdicts or memory writes
are issued by replay. Langfuse readback uses bounded observations API v2 queries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import numpy as np
import pandas as pd
from dotenv import load_dotenv

from pramana.analysis.config import load_config as analysis_config
from pramana.analysis.hypotheses.llm_proposer import ClaimBatch, render_candidate
from pramana.analysis.schema_inference import infer_schema
from pramana.api.models import RunResults
from pramana.verification.config import load_config as verification_config
from pramana.verification.executor.runner import execute
from pramana.verification.falsification.generator import FalsificationProgram

ROOT = Path(__file__).resolve().parents[1]


def mixed_run(client: httpx.Client) -> str:
    """Submit one predeclared synthetic group/trend recipe, never select by verdict."""
    months = np.repeat(np.arange(1, 7), 20)
    urban = np.tile([0, 1], 60)
    frame = pd.DataFrame(
        {
            "month": months,
            "region": np.where(urban, "urban", "rural"),
            "measure": months * 30 + urban * 100 + np.random.default_rng(20261021).normal(size=120),
        }
    )
    response = client.post(
        "/api/runs",
        files={
            "file": ("synthetic-groups-and-trend.csv", frame.to_csv(index=False)),
        },
        data={
            "user_query": "Propose group differences in measure by region and trends over month."
        },
    )
    response.raise_for_status()
    identifier = str(UUID(response.json()["run_id"]))
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{identifier}")
        response.raise_for_status()
        state = response.json()
        if state["status"] in {"completed", "degraded", "failed"}:
            if state["status"] != "completed":
                raise RuntimeError("Mixed-type acceptance did not complete; inspect local run logs")
            return identifier
        time.sleep(1)
    raise TimeoutError("Mixed-type acceptance exceeded ten minutes")


def observations(identifier: str) -> dict[str, Any]:
    """Read only model/usage metadata for this trace, never credentials or prompt I/O."""
    now = datetime.now(UTC)
    params: dict[str, Any] = {
        "fromStartTime": (now - timedelta(hours=2)).isoformat(),
        "toStartTime": now.isoformat(),
        "traceId": UUID(identifier).hex,
        "fields": "core,basic,model,usage",
        "limit": 100,
    }
    endpoint = os.environ["LANGFUSE_HOST"].rstrip("/") + "/api/public/v2/observations"
    host = urlsplit(endpoint)
    if host.scheme != "https" or host.username or host.password or host.query or host.fragment:
        raise ValueError("Use a plain HTTPS Langfuse host for this live diagnostic")
    rows: list[dict[str, Any]] = []
    with httpx.Client(
        auth=(os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"]),
        timeout=30,
        follow_redirects=False,
    ) as remote:
        for _ in range(3):
            response = remote.get(endpoint, params=params)
            if not response.is_success:
                raise RuntimeError(f"Langfuse readback returned HTTP {response.status_code}")
            body = response.json()
            rows.extend(body["data"])
            cursor = body.get("meta", {}).get("cursor")
            if not cursor:
                break
            params["cursor"] = cursor
        else:
            raise RuntimeError("Trace read exceeded the diagnostic's three-page budget")
    assert rows, "No remote observations found; do not claim tracing acceptance"
    assert all(row["traceId"] == UUID(identifier).hex for row in rows)
    generations = [row for row in rows if row.get("name") == "llm-completion"]
    assert generations and all(
        row.get("model") == os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
        for row in generations
    )
    return {
        "api_version": 2,
        "observation_count": len(rows),
        "model_requests": len(generations),
        "input_tokens": sum(row.get("usageDetails", {}).get("input", 0) for row in generations),
        "output_tokens": sum(row.get("usageDetails", {}).get("output", 0) for row in generations),
        "cost_usd": None,  # No configured/provider-resolved prices: never fabricate a zero.
        "models": sorted({row["model"] for row in generations}),
    }


def audit_run(client: httpx.Client, identifier: str, data_dir: Path) -> dict[str, Any]:
    """Require complete proofs, exact stored-source replay and matching PASS-only memory."""
    identifier = str(UUID(identifier))
    response = client.get(f"/api/runs/{identifier}/results")
    response.raise_for_status()
    result = RunResults.model_validate(response.json())
    assert result.run.status.value == "completed" and result.unverified_candidate_count == 0
    rows = [*result.verified_insights, *result.rejected_claims]
    assert rows and len(rows) == result.candidate_count
    directory = data_dir / "runs" / identifier
    frame = pd.read_pickle(directory / "cleaned.pkl")
    proposal = json.loads((directory / "analysis_proposer.json").read_text("utf-8"))
    batch = ClaimBatch.model_validate_json(proposal["response"]["message"]["content"])
    analysis = analysis_config()
    schema = infer_schema(frame, analysis.schema_inference)
    candidates = {}
    for claim in batch.claims:
        candidate = render_candidate(
            claim,
            frame,
            schema,
            analysis.hypotheses,
            dataset_ref=str(directory / "cleaned.pkl"),
            allowed=set(frame.columns),
        )
        if candidate is not None:
            candidates[candidate.insight_id] = candidate
    replayed = 0
    metrics = []
    for row in rows:
        proof = row.proof
        candidate = candidates[proof.insight_id]
        assert proof.falsification_code and row.n_permutations, "An executed proof is required"
        assert proof.test_type is not None
        config = verification_config()
        config = config.model_copy(
            update={
                "statistics": config.statistics.model_copy(
                    update={
                        "seed": proof.seed,
                        "n_permutations": row.n_permutations,
                    }
                )
            }
        )
        program = FalsificationProgram(
            insight_id=proof.insight_id,
            claim_type=candidate.claim_type,
            var_x=candidate.variables[0],
            var_y=candidate.variables[1],
            test_type=proof.test_type,
            n_permutations=row.n_permutations,
            seed=proof.seed,
            source=proof.falsification_code,
            generator="llm",
        )
        execution = execute(program, frame, config)
        assert execution.ok and execution.payload is not None, "Stored source failed replay"
        for key in (
            "p_value",
            "effect_size",
            "effect_metric",
            "reported_effect",
            "reported_effect_metric",
        ):
            assert execution.payload[key] == proof.model_dump(mode="json")[key], (
                f"Stored-source replay changed {key} for {proof.insight_id}"
            )
        replayed += 1
        metrics.append(
            {
                "insight_id": proof.insight_id,
                "claim_type": candidate.claim_type.value,
                "verdict": proof.verdict.value,
                "outcome": proof.gate_outcome.value,
                "p_value": proof.p_value,
                "q_value": proof.q_value,
                "effect_size": proof.effect_size,
                "code_sha256": hashlib.sha256(proof.falsification_code.encode()).hexdigest(),
            }
        )
    response = client.get("/api/memory")
    response.raise_for_status()
    lessons = response.json()
    assert all(lesson["proof"]["verdict"] == "PASS" for lesson in lessons)
    stored = {lesson["proof"]["insight_id"] for lesson in lessons if lesson["run_id"] == identifier}
    assert stored == {row.insight_id for row in result.verified_insights}
    trace = observations(identifier)
    assert trace["model_requests"] >= 1 + len(rows), "Missing model-call observations"
    return {
        "run_id": identifier,
        "pass_count": len(result.verified_insights),
        "reject_count": len(result.rejected_claims),
        "replayed_programs": replayed,
        "pass_only_memory": True,
        "historical_hint_count": len(result.run.past_lessons),
        "claim_types": sorted({item["claim_type"] for item in metrics}),
        "metrics": metrics,
        "trace": trace,
    }


def main() -> None:
    """Audit explicitly selected local runs; never regenerate or resubmit a family."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8081")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/deepseek-acceptance")
    parser.add_argument("--run-id", action="append", default=[])
    parser.add_argument("--mixed", action="store_true", help="Adds one paid synthetic API run")
    args = parser.parse_args()
    if urlsplit(args.url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Only a local acceptance API is allowed")
    if not args.data_dir.resolve().is_relative_to((ROOT / "data").resolve()):
        raise ValueError("Acceptance artifacts must be under the ignored repository data directory")
    load_dotenv(ROOT / ".env", override=False)
    with httpx.Client(base_url=args.url, timeout=30, follow_redirects=False) as client:
        identifiers = list(dict.fromkeys(args.run_id))
        if args.mixed:
            identifiers.append(mixed_run(client))
        if not identifiers:
            raise ValueError("Select a run with --run-id or explicitly request --mixed")
        results = [audit_run(client, identifier, args.data_dir) for identifier in identifiers]
        if args.mixed:
            assert {"group_difference", "trend"} <= set(results[-1]["claim_types"])
    report = {
        "synthetic_only": True,
        "checked_at": datetime.now(UTC).isoformat(),
        "runs": results,
        "exact_numeric_replay": True,
        "langfuse_readback": True,
    }
    target = ROOT / "artifacts/deepseek_live_acceptance.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
