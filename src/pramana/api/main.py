"""FastAPI app factory + router registration."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from pramana.api.routes import auth, datasets, memory, results, runs, system
from pramana.api.service import RunService
from pramana.common.paths import DATA_DIR
from pramana.memory.config import load_memory_settings

#: The built web UI. Docker serves it from nginx; locally `npm run build` in web/ enables it here.
WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app(*, service: RunService | None = None) -> FastAPI:
    """Build a local/private API; memory writes occur solely inside verified graph runs."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        selected = service or RunService(DATA_DIR, load_memory_settings())
        selected.repository.recover_interrupted()
        application.state.run_service = selected
        yield

    application = FastAPI(title="PRAMANA", version="0.1.0", lifespan=lifespan)
    application.include_router(auth.router, prefix="/api")
    application.include_router(datasets.router, prefix="/api")
    application.include_router(runs.router, prefix="/api")
    application.include_router(results.router, prefix="/api")
    application.include_router(memory.router, prefix="/api")
    application.include_router(system.router, prefix="/api")

    @application.middleware("http")
    async def same_origin_writes(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Refuse cross-site writes: a browser's Origin must match the host it called."""
        origin = request.headers.get("origin")
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and origin
            and urlsplit(origin).netloc != request.headers.get("host")
        ):
            return JSONResponse({"detail": "Cross-site request refused."}, status_code=403)
        return await call_next(request)

    @application.get("/health")
    def health() -> dict[str, str]:
        """Report API liveness; this is not a claim that external dependencies are healthy."""
        return {"status": "ok"}

    if WEB_DIST.is_dir():
        application.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")

    return application


app = create_app()
