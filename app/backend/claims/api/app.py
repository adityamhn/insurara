"""FastAPI application factory.

`create_app()` builds the default SQLite-backed app; tests pass a seeded session
factory to run against a temp database. CORS is open for the local Next.js dev server.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from ..mcp.reviewer import create_reviewer_mcp
from ..persistence.db import init_db, make_engine, make_session_factory
from .errors import register_error_handlers
from .routers import claims, disputes, reference


def _allowed_origins() -> list[str]:
    """Local reviewer origins allowed to call the API from a browser.

    CLAIMS_ALLOWED_ORIGINS can override this with a comma-separated list when the
    UI is served from a different local port.
    """
    configured = os.environ.get("CLAIMS_ALLOWED_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]


def create_app(session_factory: sessionmaker[Session] | None = None) -> FastAPI:
    if session_factory is None:
        engine = make_engine()
        init_db(engine)
        session_factory = make_session_factory(engine)

    # The mounted MCP app runs a StreamableHTTPSessionManager whose task group is started
    # by its own lifespan. Mounting alone doesn't run a sub-app's lifespan, so we propagate
    # it through the parent app's lifespan — otherwise /mcp 500s with
    # "Task group is not initialized".
    mcp_app = create_reviewer_mcp(session_factory).streamable_http_app()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    app = FastAPI(title="Claims Processing System", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)
    app.include_router(reference.router)
    app.include_router(claims.router)
    app.include_router(disputes.router)
    app.mount("/mcp", mcp_app)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


# Module-level app for `uvicorn claims.api.app:app` (uses the default DB).
app = create_app()
