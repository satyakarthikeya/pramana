"""Check a true pair and an explicitly weak shuffled decoy through the actual V1 API."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import numpy as np

from pramana.api.models import RunResults
from pramana.api.v1 import sample_frame, v1_settings
from pramana.memory.lesson import Lesson


def main() -> None:
    """Require complete executed proofs and PASS-only writes; never synthesize verdicts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8081")
    args = parser.parse_args()
    if urlsplit(args.url).hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("This synthetic acceptance script is for a local app only")
    settings = v1_settings()
    frame = sample_frame()[["age_years", "systolic_bp"]].head(settings.sample_pilot_rows).copy()
    rng = np.random.default_rng(settings.sample_seed)
    # Choose a weak exploratory correlation before running the gate; no p-value or
    # verdict is used to select the permutation. This is a demo, not FDR evaluation.
    shuffled = [rng.permutation(frame["age_years"].to_numpy()) for _ in range(200)]
    source = frame["age_years"]
    import pandas as pd

    frame["shuffled_decoy"] = min(
        shuffled,
        key=lambda values: abs(
            pd.Series(values, index=source.index).corr(source, method="spearman")
            - settings.sample_decoy_rho
        ),
    )
    with httpx.Client(base_url=args.url, timeout=30) as client:
        response = client.post(
            "/api/runs", files={"file": ("synthetic-shuffled-check.csv", frame.to_csv(index=False))}
        )
        response.raise_for_status()
        run_id = response.json()["run_id"]
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            response = client.get(f"/api/runs/{run_id}")
            response.raise_for_status()
            view = response.json()
            if view["status"] in {"completed", "degraded", "failed"}:
                break
            time.sleep(1)
        else:
            raise TimeoutError("V1 truth run exceeded ten minutes")
        if view["status"] != "completed":
            raise RuntimeError(f"V1 truth run did not complete: {view['status']}")
        response = client.get(f"/api/runs/{run_id}/results")
        response.raise_for_status()
        result = RunResults.model_validate(response.json())
        assert result.unverified_candidate_count == 0
        assert any(
            "age_years" in row.claim and "systolic_bp" in row.claim
            for row in result.verified_insights
        )
        assert any("shuffled_decoy" in row.claim for row in result.rejected_claims)
        lessons = [Lesson.model_validate(item) for item in client.get("/api/memory").json()]
        stored = {lesson.proof.insight_id for lesson in lessons if lesson.run_id == run_id}
        assert stored == {row.insight_id for row in result.verified_insights}
        report = {
            "synthetic": True,
            "purpose": "selected weak shuffled decoy demo, not FDR study",
            "run_id": run_id,
            "build_seed": settings.sample_seed,
            "pass_only_memory": True,
            "results": result.model_dump(mode="json"),
        }
        target = Path("artifacts/v1_truth.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"PASS: true pair supported, shuffled decoy rejected, memory guarded; {run_id}")


if __name__ == "__main__":
    main()
