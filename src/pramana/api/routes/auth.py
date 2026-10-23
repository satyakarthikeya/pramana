"""Sign up, sign in, sign out and "who am I" with an HttpOnly session cookie."""

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from pramana.api.auth import (
    MAX_EMAIL,
    MAX_PASSWORD,
    SESSION_COOKIE,
    SESSION_DAYS,
    AuthError,
    TooManyAttempts,
    User,
)
from pramana.api.deps import current_user, get_service
from pramana.api.service import RunService

router = APIRouter(prefix="/auth", tags=["auth"])
Service = Annotated[RunService, Depends(get_service)]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=MAX_EMAIL)
    password: str = Field(max_length=MAX_PASSWORD)


def client_address(request: Request) -> str:
    """The caller's address. Behind our own nginx (PRAMANA_TRUST_PROXY=1) that is the first
    X-Forwarded-For entry; otherwise it is the socket peer. Never trust the header on a
    server that is reachable without the proxy."""
    if os.getenv("PRAMANA_TRUST_PROXY") == "1":
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "?"


def _signup_open() -> bool:
    return os.getenv("PRAMANA_ALLOW_SIGNUP", "1") != "0"


def _start_session(service: RunService, response: Response, user: User) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        service.auth.open_session(user),
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=os.getenv("PRAMANA_COOKIE_SECURE") == "1",
        path="/",
    )


@router.post("/signup", response_model=User, status_code=201)
def signup(body: Credentials, request: Request, response: Response, service: Service) -> User:
    try:
        user, first = service.auth.signup(
            body.email,
            body.password,
            allow_signup=_signup_open(),
            client=client_address(request),
        )
    except TooManyAttempts as error:
        raise HTTPException(429, str(error)) from None
    except AuthError as error:
        raise HTTPException(403 if "closed" in str(error) else 422, str(error)) from None
    if first:
        # Anything stored before accounts existed belongs to the first person to sign up.
        service.repository.claim_unowned(user.user_id)
        service.datasets.claim_unowned(user.user_id)
    _start_session(service, response, user)
    return user


@router.post("/login", response_model=User)
def login(body: Credentials, request: Request, response: Response, service: Service) -> User:
    try:
        user = service.auth.login(body.email, body.password, client=client_address(request))
    except TooManyAttempts as error:
        raise HTTPException(429, str(error)) from None
    except AuthError as error:
        raise HTTPException(401, str(error)) from None
    _start_session(service, response, user)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, service: Service) -> None:
    service.auth.close_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=User)
def me(user: Annotated[User, Depends(current_user)]) -> User:
    return user


@router.get("/status")
def status(service: Service) -> dict[str, bool]:
    """Tell the sign-in screen whether this server has any account yet (first-run setup)."""
    return {"has_accounts": service.auth.user_count() > 0, "signup_open": _signup_open()}
