"""One-command local V1 startup; explicit offline mode is not a fallback."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> None:
    """Start local V1 with documented defaults and explicit model opt-in."""
    from dotenv import load_dotenv

    # Load the environment before importing paths that resolve PRAMANA_DATA_DIR.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    from pramana.api.v1 import v1_settings

    parser = argparse.ArgumentParser(description="Start the local PRAMANA V1 app")
    parser.add_argument("--generator", choices=("template", "llm"))
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    if args.generator:
        os.environ["PRAMANA_VERIFICATION_GENERATOR"] = args.generator
    os.environ.setdefault("PRAMANA_VERIFICATION_GENERATOR", v1_settings().generator)
    os.environ.setdefault("PRAMANA_API_VERIFICATION_MODE", "inprocess")
    generator = os.environ["PRAMANA_VERIFICATION_GENERATOR"]
    if generator == "template":
        os.environ.setdefault("PRAMANA_LANGFUSE_ENABLED", "false")
    print(f"PRAMANA V1: {generator} verification; http://127.0.0.1:{args.port}")
    import uvicorn

    uvicorn.run("pramana.api.main:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
