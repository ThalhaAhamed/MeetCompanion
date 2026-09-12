"""
FastAPI application entry point for Meet Companion.
"""
from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.health import router as health_router
from app.api.webhooks import router as webhooks_router
from app.api.meetings import router as meetings_router
from app.api.documents import router as documents_router
from app.api.agent import router as agent_router
from app.api.search import router as search_router
from app.api.action_items import router as action_items_router
from app.api.graph import router as graph_router
from app.api.auth import router as auth_router
from app.api.members import router as members_router
from app.api.setup import router as setup_router
from app.api.notebook import router as notebook_router
from app.mcp.server import router as mcp_router
from app.middleware.auth_gate import AuthGateMiddleware
from app.services.embedding import embedding_service
from app.database.bootstrap import bootstrap
from app.database.connection import current_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown procedures."""
    print(f"[{settings.APP_NAME}] Application starting up in {settings.APP_ENV} mode...")
    await bootstrap(current_engine())
    # Load the embedding model now, in a background thread, so the first real
    # search/index request isn't the one paying the multi-second model load
    # cost (and blocking the event loop while it loads).
    import asyncio
    asyncio.create_task(embedding_service.warmup_async())
    yield
    print(f"[{settings.APP_NAME}] Application shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    description="Persistent AI Meeting Companion using MeetStream MIA and pgvector RAG.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Per-member session gate (see app/middleware/auth_gate.py). Registered
# BEFORE CORSMiddleware so that CORS ends up as the outermost layer -
# Starlette wraps middleware in reverse registration order, and a 401 this
# gate returns directly (short-circuiting call_next) never reaches an inner
# CORSMiddleware to get CORS headers added, which the browser then reports
# as an opaque "Failed to fetch" / CORS error instead of a real 401.
app.add_middleware(AuthGateMiddleware)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router)
app.include_router(setup_router)
app.include_router(webhooks_router)
app.include_router(auth_router)
app.include_router(members_router)
app.include_router(meetings_router)
app.include_router(documents_router)
app.include_router(agent_router)
app.include_router(search_router)
app.include_router(action_items_router)
app.include_router(graph_router)
app.include_router(notebook_router)
app.include_router(mcp_router)


def _static_dir() -> Optional[Path]:
    """
    The built web UI, when the server is meant to serve it itself.

    Set MEET_COMPANION_STATIC_DIR explicitly (the desktop bundle does), or
    build the frontend into frontend/dist for a single-process deployment.
    During development Vite serves the UI on its own port and this is None.
    """
    configured = os.environ.get("MEET_COMPANION_STATIC_DIR")
    candidates = [Path(configured)] if configured else [Path(__file__).resolve().parents[1] / "frontend" / "dist"]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


STATIC_DIR = _static_dir()

if STATIC_DIR is None:

    @app.get("/")
    async def root():
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "online",
            "docs_url": "/docs",
            "mcp_endpoint": "/mcp",
        }

else:
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        """Files from the build when they exist; index.html for every app route."""
        if path and not path.startswith("api/"):
            candidate = (STATIC_DIR / path).resolve()
            if candidate.is_file() and STATIC_DIR in candidate.parents:
                return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
