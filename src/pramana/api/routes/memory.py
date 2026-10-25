"""Memory browse/search (read-only, signed-in users). Writes never go through the API.

The store is one collection, but each account sees only lessons from its own runs: a
lesson's text names another person's columns and findings.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from pramana.api.auth import User
from pramana.api.deps import current_user, get_service
from pramana.api.models import MemorySearch
from pramana.api.service import RunService
from pramana.memory.lesson import Lesson
from pramana.memory.retrieval import RetrievedLesson

router = APIRouter(prefix="/memory", tags=["memory"])
Service = Annotated[RunService, Depends(get_service)]
Owner = Annotated[User, Depends(current_user)]


@router.get("", response_model=list[Lesson])
def browse_memory(
    service: Service,
    user: Owner,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Lesson]:
    """Browse this account's verified lessons through the store boundary; never write."""
    try:
        mine = service.repository.run_ids(user.user_id)
        found: list[Lesson] = []
        page = 0
        while len(found) < offset + limit:
            batch = service.store.browse(limit=100, offset=page)
            found.extend(lesson for lesson in batch if lesson.run_id in mine)
            if len(batch) < 100:
                break
            page += 100
        return found[offset : offset + limit]
    except Exception:
        raise HTTPException(503, "Verified memory is unavailable or failed validation.") from None


@router.post("/search", response_model=list[RetrievedLesson])
def search_memory(request: MemorySearch, service: Service, user: Owner) -> list[RetrievedLesson]:
    """Return historical hints only; similarity is not statistical evidence."""
    try:
        mine = service.repository.run_ids(user.user_id)
        return [
            RetrievedLesson(lesson=lesson, similarity=similarity)
            for lesson, similarity in service.store.search(request.query, top_k=request.top_k)
            if lesson.run_id in mine
        ]
    except Exception:
        raise HTTPException(503, "Verified memory search is unavailable.") from None
