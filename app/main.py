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
from app.mcp.server import router as mcp_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown procedures."""
    print(f"[{settings.APP_NAME}] Application starting up in {settings.APP_ENV} mode...")
    yield
    print(f"[{settings.APP_NAME}] Application shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    description="Persistent AI Meeting Companion using MeetStream MIA and pgvector RAG.",
    version="1.0.0",
    lifespan=lifespan,
)

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
app.include_router(meetings_router)
app.include_router(documents_router)
app.include_router(agent_router)
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
