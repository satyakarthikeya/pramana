"""Chat with a stored dataset: ask a question, read the conversation, read the testing ledger."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from pramana.api.auth import User
from pramana.api.deps import current_user, get_service
from pramana.api.service import RunService
from pramana.chat.models import ChatExchange, ChatLedger, ChatQuestion
from pramana.chat.service import ChatInputError, ChatRateLimited, ChatUnavailable

router = APIRouter(prefix="/datasets/{dataset_id}/chat", tags=["chat"])
Service = Annotated[RunService, Depends(get_service)]
Owner = Annotated[User, Depends(current_user)]


@router.get("", response_model=list[ChatExchange])
def conversation(dataset_id: UUID, service: Service, user: Owner) -> list[ChatExchange]:
    try:
        return service.chat.history(dataset_id, user.user_id)
    except KeyError:
        raise HTTPException(404, "Dataset not found.") from None


@router.post("", response_model=ChatExchange)
def ask(dataset_id: UUID, body: ChatQuestion, service: Service, user: Owner) -> ChatExchange:
    """Answer one question. Fails closed with a plain message when the model is unavailable."""
    try:
        return service.chat.ask(dataset_id, user.user_id, body.question)
    except KeyError:
        raise HTTPException(404, "Dataset not found.") from None
    except ChatInputError as error:
        raise HTTPException(422, str(error)) from None
    except ChatRateLimited as error:
        raise HTTPException(429, str(error)) from None
    except ChatUnavailable as error:
        raise HTTPException(503, str(error)) from None


@router.get("/tests", response_model=ChatLedger)
def testing_ledger(dataset_id: UUID, service: Service, user: Owner) -> ChatLedger:
    """Every claim chat has sent to the gateway on this dataset, in order."""
    try:
        return service.chat.ledger(dataset_id, user.user_id)
    except KeyError:
        raise HTTPException(404, "Dataset not found.") from None
