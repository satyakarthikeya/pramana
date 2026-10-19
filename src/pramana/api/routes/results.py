"""GET results: insights with their full proof objects.

Owner: M. Karthik Reddy
Scope: scope/SCOPE_M_Karthik_Reddy.md
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from pramana.api.deps import get_service
from pramana.api.models import RunResults
from pramana.api.service import RunService

router = APIRouter(tags=["results"])


@router.get("/runs/{run_id}/results", response_model=RunResults)
def get_results(run_id: UUID, service: Annotated[RunService, Depends(get_service)]) -> RunResults:
    """Publish PASS findings separately from rejected claims, each with its original proof."""
    try:
        result = service.repository.results(run_id)
    except KeyError:
        raise HTTPException(404, "Run not found.") from None
    if result is None:
        raise HTTPException(409, "No result snapshot is available for this run.")
    return result
