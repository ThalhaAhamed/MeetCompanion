"""
Health check endpoints for service and dependency monitoring.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database.connection import get_db
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Basic liveness check."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
    }


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness check verifying database connectivity and pgvector extension."""
    db_healthy = False
    pgvector_available = False
    details = {}

    try:
        res = await db.execute(text("SELECT 1"))
        if res.scalar() == 1:
            db_healthy = True

        vec_res = await db.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
        if vec_res.scalar() == "vector":
            pgvector_available = True
    except Exception as e:
        details["error"] = str(e)

    overall_status = "ready" if (db_healthy and pgvector_available) else "degraded"

    return {
        "status": overall_status,
        "database": "connected" if db_healthy else "disconnected",
        "pgvector": "installed" if pgvector_available else "missing",
        "details": details,
    }
