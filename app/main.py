"""
FastAPI application entry point for MeetStream Companion.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.health import router as health_router
from app.api.webhooks import router as webhooks_router
from app.api.meetings import router as meetings_router
from app.api.documents import router as documents_router
from app.api.agent import router as agent_router
from app.api.search import router as search_router
from app.api.action_items import router as action_items_router
from app.api.auth import router as auth_router
from app.api.members import router as members_router
from app.mcp.server import router as mcp_router
from app.middleware.auth_gate import AuthGateMiddleware
from app.services.embedding import embedding_service
from app.database.connection import engine
from sqlalchemy import text


async def _ensure_schema():
    """
    Idempotent additive schema patches for columns added after the initial
    migrations/001_initial_schema.sql was applied - there's no migration
    runner wired into deploys, so new columns are added here with
    IF NOT EXISTS guards rather than requiring a manual psql step per deploy.
    """
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE"))
        await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS mcp_token VARCHAR(255) UNIQUE"))
        await conn.execute(text("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS join_code VARCHAR(50) UNIQUE"))
        # The existing default-org workspace's live MeetStream agent is already
        # wired with the single global MCP_AUTH_TOKEN from before per-workspace
        # tokens existed - backfill it as that org's own mcp_token so its agent
        # keeps working without needing to be re-wired.
        if settings.MCP_AUTH_TOKEN:
            await conn.execute(
                text(
                    "UPDATE organizations SET mcp_token = :token "
                    "WHERE id = :org_id AND mcp_token IS NULL"
                ),
                {"token": settings.MCP_AUTH_TOKEN, "org_id": settings.DEFAULT_ORG_ID},
            )
        await conn.execute(
            text(
                "UPDATE organizations SET join_code = substr(md5(random()::text), 1, 8) "
                "WHERE join_code IS NULL"
            )
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown procedures."""
    print(f"[{settings.APP_NAME}] Application starting up in {settings.APP_ENV} mode...")
    await _ensure_schema()
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
    version="1.0.0",
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
app.include_router(webhooks_router)
app.include_router(auth_router)
app.include_router(members_router)
app.include_router(meetings_router)
app.include_router(documents_router)
app.include_router(agent_router)
app.include_router(search_router)
app.include_router(action_items_router)
app.include_router(mcp_router)


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "status": "online",
        "docs_url": "/docs",
        "mcp_endpoint": "/mcp",
    }
