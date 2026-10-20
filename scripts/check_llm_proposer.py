"""Preflight or exercise the real, traced local claim proposer on synthetic data."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pramana.analysis.config import load_config  # noqa: E402
from pramana.analysis.hypotheses.generation import generate_candidates  # noqa: E402
from pramana.analysis.schema_inference import infer_schema  # noqa: E402
from pramana.common.config import load_runtime_config  # noqa: E402
from pramana.common.langfuse_client import get_langfuse_client  # noqa: E402
from pramana.common.logging import bind_run_context, clear_log_context  # noqa: E402


def main() -> int:
    """Check local Ollama and the explicitly chosen local/Langfuse audit backend."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--verify", action="store_true", help="Verify the returned batch once")
    parser.add_argument("--trace-backend", choices=["local", "langfuse"])
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    config = load_config()
    settings = config.hypotheses.proposer.model_copy(update={"engine": "ollama"})
    if args.trace_backend:
        settings = settings.model_copy(update={"trace_backend": args.trace_backend})
    hypotheses = config.hypotheses.model_copy(update={"proposer": settings})
    tracing = None
    try:
        if settings.trace_backend == "langfuse":
            tracing = get_langfuse_client(load_runtime_config().langfuse)
            if tracing is None or not tracing.auth_check():
                raise RuntimeError("Langfuse credentials were not accepted")
        import ollama

        info = ollama.Client(host=settings.base_url, timeout=10, trust_env=False).show(
            settings.model
        )
        details = info.model_dump(mode="json") if hasattr(info, "model_dump") else dict(info)
        family = str(details.get("details", {}).get("family", ""))
        if not family.startswith("gemma"):
            raise RuntimeError("The installed model does not report a Gemma family")
    except Exception as error:
        print(f"BLOCKED: preflight failed ({type(error).__name__}); no model inference was made.")
        return 2
    print(
        f"Preflight passed: {settings.model}; audit backend: {settings.trace_backend}.", flush=True
    )
    if args.preflight_only:
        return 0
    run_id = uuid4()
    rng = np.random.default_rng(settings.seed)
    age = rng.uniform(20, 80, 120)
    frame = pd.DataFrame(
        {
            "age": age,
            "bmi": age * 0.2 + rng.normal(0, 1, len(age)),
            "region": np.tile(["urban", "rural"], 60),
            "noise": rng.normal(size=len(age)),
        }
    )
    schema = infer_schema(frame, config.schema_inference)
    bind_run_context(str(run_id))
    started = time.monotonic()
    try:
        candidates = generate_candidates(
            frame,
            schema,
            hypotheses,
            dataset_ref=f"synthetic-proposer:{run_id}",
            run_id=run_id,
            user_query="Propose a few numeric associations or group differences to test.",
        )
        report = {
            "run_id": str(run_id),
            "model": settings.model,
            "seed": settings.seed,
            "candidate_count_unverified": len(candidates),
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "synthetic_data_only": True,
            "trace_backend": settings.trace_backend,
        }
        if args.verify:
            from pramana.verification.config import load_config as gateway_config
            from pramana.verification.gateway import verify_batch

            proofs = verify_batch(candidates, frame, gateway_config())
            report["proofs"] = [proof.model_dump(mode="json") for proof in proofs]
            print(
                f"Verification complete: {sum(p.verdict.value == 'PASS' for p in proofs)} PASS, "
                f"{sum(p.verdict.value == 'REJECT' for p in proofs)} REJECT.",
                flush=True,
            )
        target = ROOT / "artifacts" / f"llm_proposer_{run_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        if tracing is not None:
            tracing.flush()
        print(f"Completed: {len(candidates)} unverified proposals; report: {target}")
        return 0
    finally:
        clear_log_context()


if __name__ == "__main__":
    raise SystemExit(main())
