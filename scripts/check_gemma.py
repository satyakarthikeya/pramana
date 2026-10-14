"""Check a traced local Gemma setup using synthetic column data only."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from pramana.analysis import infer_schema, load_config  # noqa: E402
from pramana.analysis.schema_inference import ColumnRole  # noqa: E402
from pramana.common.config import load_runtime_config  # noqa: E402
from pramana.common.langfuse_client import get_langfuse_client  # noqa: E402
from pramana.common.logging import configure_logging  # noqa: E402


def main() -> int:
    """Return success only when a traced local model classified the synthetic column."""
    load_dotenv(REPO_ROOT / ".env")
    configure_logging()
    required = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        print("Live check needs locally configured settings: " + ", ".join(missing))
        return 2
    client = get_langfuse_client(load_runtime_config().langfuse)
    if client is None or not client.auth_check():
        print("Live check cannot proceed: Langfuse is disabled or authentication failed.")
        return 2
    run_id = uuid4()
    data = pd.DataFrame({"encoded_measurement": [str(index) for index in range(40)]})
    schema = infer_schema(data, load_config().schema_inference, run_id=run_id)
    client.flush()
    print(f"Run {run_id}: synthetic column role = {schema.role_of('encoded_measurement').value}")
    return 0 if schema.role_of("encoded_measurement") is ColumnRole.NUMERIC else 1


if __name__ == "__main__":
    raise SystemExit(main())
