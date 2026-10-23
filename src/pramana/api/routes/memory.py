"""Memory browse/search (read-only, signed-in users). Writes never go through the API.

Memory is still shared between accounts; separating it per user is a later decision.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from pramana.api.deps import current_user, get_service
from pramana.api.models import MemorySearch
from pramana.api.service import RunService
from pramana.memory.lesson import Lesson
from pramana.memory.retrieval import RetrievedLesson

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(current_user)])
Service = Annotated[RunService, Depends(get_service)]


@router.get("", response_model=list[Lesson])
def browse_memory(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Lesson]:
    """Browse verified source lessons through the store boundary; never write memory."""
    try:
        return service.store.browse(limit=limit, offset=offset)
    except Exception:
        raise HTTPException(503, "Verified memory is unavailable or failed validation.") from None


@router.post("/search", response_model=list[RetrievedLesson])
def search_memory(request: MemorySearch, service: Service) -> list[RetrievedLesson]:
    """Return historical hints only; similarity is not statistical evidence."""
    try:
        return [
            RetrievedLesson(lesson=lesson, similarity=similarity)
            for lesson, similarity in service.store.search(request.query, top_k=request.top_k)
        ]
    except Exception:
        raise HTTPException(503, "Verified memory search is unavailable.") from None
