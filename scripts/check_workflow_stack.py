"""Upload synthetic data to a running stack and check proofs and guarded persistence."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pramana.api.models import RunResults  # noqa: E402
from pramana.memory.lesson import Lesson  # noqa: E402
from pramana.verification.config import load_config  # noqa: E402


def main() -> None:
    """Require a completed real run, a proof for every claim and PASS-only memory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--startup-timeout", type=float, default=120)
    parser.add_argument("--run-timeout", type=float, default=600)
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=15, trust_env=False) as client:
        deadline = time.monotonic() + args.startup_timeout
        while True:
            try:
                client.get("/health").raise_for_status()
                break
            except httpx.HTTPError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Stack did not become reachable") from None
                time.sleep(2)
        config = load_config()
        rng = np.random.default_rng(config.statistics.seed)
        age = rng.normal(45, 10, 120)
        frame = pd.DataFrame(
            {
                "age": age,
                "bmi": age * 0.3 + rng.normal(0, 0.1, len(age)),
                "noise": rng.normal(size=len(age)),
            }
        )
        upload = client.post(
            "/api/runs",
            files={"file": ("workflow-smoke.csv", frame.to_csv(index=False))},
            data={"user_query": "Which health measurements are associated with age?"},
        )
        upload.raise_for_status()
        run_id = upload.json()["run_id"]
        deadline = time.monotonic() + args.run_timeout
        previous = None
        while True:
            response = client.get(f"/api/runs/{run_id}")
            response.raise_for_status()
            view = response.json()
            if view["status"] != previous:
                print(f"{run_id}: {view['status']}", flush=True)
                previous = view["status"]
            if view["status"] in {"completed", "degraded", "failed"}:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Run {run_id} did not finish before the smoke deadline")
            time.sleep(2)
        if view["status"] != "completed":
            raise RuntimeError(f"Run {run_id} finished as {view['status']}: {view.get('error')}")
        response = client.get(f"/api/runs/{run_id}/results")
        response.raise_for_status()
        result = RunResults.model_validate(response.json())
        if result.unverified_candidate_count or not result.verified_insights:
            raise RuntimeError("Smoke run needs complete proofs and at least one real PASS")
        response = client.get("/api/memory", params={"limit": 100})
        response.raise_for_status()
        stored = [Lesson.model_validate(item) for item in response.json()]
        stored_ids = {item.proof.insight_id for item in stored if item.run_id == run_id}
        passed = {row.insight_id for row in result.verified_insights}
        rejected = {row.insight_id for row in result.rejected_claims}
        if not passed <= stored_ids or rejected & stored_ids:
            raise RuntimeError("Persistent memory does not match the run's PASS-only output")
        report = {
            "synthetic_data_only": True,
            "run_id": run_id,
            "pass_count": len(passed),
            "reject_count": len(rejected),
            "pass_only_persistence": True,
            "results": result.model_dump(mode="json"),
        }
        target = ROOT / "artifacts/workflow_stack_smoke.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Passed: {len(passed)} PASS, {len(rejected)} REJECT; report: {target}")


if __name__ == "__main__":
    main()
