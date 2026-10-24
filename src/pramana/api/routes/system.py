"""What this server is configured to do, and what is missing, without exposing any secret."""

import os
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from pramana.analysis import load_config
from pramana.analysis.workspace import AgentConfig, load_workspace_config
from pramana.api.auth import User
from pramana.api.deps import current_user
from pramana.verification.config import load_config as load_verification_config

router = APIRouter(prefix="/system", tags=["system"])


class SystemStatus(BaseModel):
    analysis_engine: str
    verification_generator: str
    model: str | None
    #: True when every model-driven part that is switched on can actually run.
    model_ready: bool
    #: Plain names of what is missing; never values.
    blockers: list[str]
    budgets: AgentConfig
    #: Chat always needs a model; these name what is missing for it (never values).
    chat_ready: bool
    chat_blockers: list[str]


@router.get("", response_model=SystemStatus)
def system_status(_user: Annotated[User, Depends(current_user)]) -> SystemStatus:
    proposer = load_config().hypotheses.proposer
    generator = (
        os.getenv("PRAMANA_VERIFICATION_GENERATOR") or load_verification_config().llm.generator
    )
    uses_model = proposer.engine in {"api", "agent", "planner"} or generator == "llm"
    blockers: list[str] = []
    if uses_model:
        if not os.getenv("DEEPSEEK_API_KEY"):
            blockers.append("DEEPSEEK_API_KEY is not set")
        if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
            blockers.append("Langfuse keys are not set (model calls must be traced)")
    chat_blockers: list[str] = []
    if not os.getenv("DEEPSEEK_API_KEY"):
        chat_blockers.append("DEEPSEEK_API_KEY is not set")
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        chat_blockers.append("Langfuse keys are not set (model calls must be traced)")
    return SystemStatus(
        analysis_engine=proposer.engine,
        verification_generator=generator,
        model=proposer.api_model if uses_model else None,
        model_ready=uses_model and not blockers,
        blockers=blockers,
        budgets=load_workspace_config().agent,
        chat_ready=not chat_blockers,
        chat_blockers=chat_blockers,
    )
