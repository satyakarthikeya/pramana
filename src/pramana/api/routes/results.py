"""GET results: insights with their full proof objects.

Owner: M. Karthik Reddy
Scope: scope/SCOPE_M_Karthik_Reddy.md
"""

import csv
import io
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from pramana.api.auth import User
from pramana.api.deps import current_user, get_service
from pramana.api.models import RunResults
from pramana.api.service import RunService

router = APIRouter(tags=["results"])


@router.get("/runs/{run_id}/results", response_model=RunResults)
def get_results(
    run_id: UUID,
    service: Annotated[RunService, Depends(get_service)],
    user: Annotated[User, Depends(current_user)],
) -> RunResults:
    """Publish PASS findings separately from rejected claims, each with its original proof."""
    try:
        result = service.repository.results(run_id, user.user_id)
    except KeyError:
        raise HTTPException(404, "Run not found.") from None
    if result is None:
        raise HTTPException(409, "No result snapshot is available for this run.")
    return result


@router.get("/runs/{run_id}/export/{format}")
def export_results(
    run_id: UUID,
    format: str,
    service: Annotated[RunService, Depends(get_service)],
    user: Annotated[User, Depends(current_user)],
) -> Response:
    """Export only proof-bearing results, explicitly separating findings and rejections."""
    if format not in {"json", "csv"}:
        raise HTTPException(404, "Choose JSON or CSV export.")
    result = get_results(run_id, service, user)
    if format == "json":
        body, media = result.model_dump_json(), "application/json"
    else:
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            [
                "insight_id",
                "claim",
                "is_finding",
                "verdict",
                "reason",
                "q_value",
                "effect_size",
                "effect_metric",
                "complete_rows",
                "seed",
            ]
        )
        for row in result.verified_insights + result.rejected_claims:

            def cell(value: object) -> str:
                # Numbers and booleans are written as they are (a negative effect stays a
                # number); only free text can start a spreadsheet formula.
                if value is None:
                    return ""
                if isinstance(value, bool | int | float):
                    return str(value)
                text = str(value)
                risky = text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) or text.startswith(
                    ("\t", "\r")
                )
                return "'" + text if risky else text

            proof = row.proof
            writer.writerow(
                [
                    cell(value)
                    for value in [
                        row.insight_id,
                        row.claim,
                        proof.verdict.value == "PASS",
                        proof.verdict.value,
                        row.explanation,
                        proof.q_value,
                        proof.effect_size,
                        proof.effect_metric.value if proof.effect_metric else None,
                        row.complete_rows,
                        proof.seed,
                    ]
                ]
            )
        body, media = output.getvalue(), "text/csv"
    return Response(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="pramana-{run_id}.{format}"'},
    )
