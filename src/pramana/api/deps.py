"""Shared dependencies: config, store handles, auth/secrets from env.
Secrets (DeepSeek API key) come from the environment, never the repo.

Owner: M. Karthik Reddy
Scope: scope/SCOPE_M_Karthik_Reddy.md
"""

from typing import cast

from fastapi import Request

from pramana.api.service import RunService


def get_service(request: Request) -> RunService:
    """Return the lifespan-owned service; no request can select a storage backend."""
    return cast(RunService, request.app.state.run_service)
