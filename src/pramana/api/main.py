"""FastAPI app factory + router registration.

TODO(karthik-reddy): SCOPE_M 4 step 5.

Owner: M. Karthik Reddy
Scope: scope/SCOPE_M_Karthik_Reddy.md
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pramana.api.routes import memory, results, runs
from pramana.api.service import RunService
from pramana.common.paths import DATA_DIR
from pramana.memory.config import load_memory_settings

DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "dashboard/static"


def create_app(*, service: RunService | None = None) -> FastAPI:
    """Build a local/private API; memory writes occur solely inside verified graph runs."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        selected = service or RunService(DATA_DIR, load_memory_settings())
        selected.repository.recover_interrupted()
        application.state.run_service = selected
        yield

    application = FastAPI(title="PRAMANA", version="0.1.0", lifespan=lifespan)
    application.include_router(runs.router, prefix="/api")
    application.include_router(results.router, prefix="/api")
    application.include_router(memory.router, prefix="/api")
    application.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="dashboard")

    @application.get("/health")
    def health() -> dict[str, str]:
        """Report API liveness; this is not a claim that external dependencies are healthy."""
        return {"status": "ok"}

    @application.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        """Serve the dashboard that consumes only public, read-only result interfaces."""
        return FileResponse(DASHBOARD_DIR / "index.html")

    return application


app = create_app()
