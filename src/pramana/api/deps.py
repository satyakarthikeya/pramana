"""Shared dependencies: the run service and the signed-in user."""

from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request

from pramana.api.auth import SESSION_COOKIE, User
from pramana.api.service import RunService


def get_service(request: Request) -> RunService:
    """Return the lifespan-owned service; no request can select a storage backend."""
    return cast(RunService, request.app.state.run_service)


def current_user(request: Request, service: Annotated[RunService, Depends(get_service)]) -> User:
    """Require a valid session; every data route depends on this."""
    user = service.auth.user_for(request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(401, "Sign in to continue.")
    return user
