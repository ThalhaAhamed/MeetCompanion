"""
Pytest configuration and shared fixtures.

The suite is hermetic: it runs against a throwaway local SQLite file and needs
no Postgres server, no Docker and no network. DATABASE_URL is set before any
application module is imported, because the engine is constructed at import
time from settings.
"""
import os
import tempfile
from pathlib import Path

TEST_DB_PATH = Path(tempfile.gettempdir()) / "meet_companion_test.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.database.connection import engine  # noqa: E402
from app.main import app, _ensure_default_workspace  # noqa: E402
from app.models.database import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def event_loop_policy():
    import asyncio

    return asyncio.get_event_loop_policy()


@pytest_asyncio.fixture(autouse=True)
async def database_schema():
    """
    Bring the database to the same state a fresh install starts in: schema
    created and the default workspace bootstrapped.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_default_workspace()
    yield


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client for the FastAPI application."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
