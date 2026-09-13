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

# Point TEST_DATABASE_URL at a Postgres server (pgvector installed) to run
# the same suite against the Postgres backend - CI does this with a service
# container. Anything else, or nothing, means the throwaway SQLite file.
TEST_DB_PATH = Path(tempfile.gettempdir()) / "meet_companion_test.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
# Secrets are generated per install and placeholders are refused; the suite
# supplies real-looking ones so nothing is written next to a developer's data.
os.environ.setdefault("SESSION_SECRET", "test-session-secret-not-for-production-0123456789")
os.environ.setdefault("MCP_AUTH_TOKEN", "test-mcp-token-not-for-production-0123456789")

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.database.connection import current_engine  # noqa: E402
from app.database.bootstrap import bootstrap  # noqa: E402
from app.main import app  # noqa: E402
from app.models.database import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def event_loop_policy():
    import asyncio

    return asyncio.get_event_loop_policy()


@pytest_asyncio.fixture(autouse=True)
async def database_schema():
    """
    Give every test the state a fresh install starts in.

    The schema is rebuilt per test rather than merely created once, so rows
    written by one test cannot leak into the next and make assertions about
    counts or ordering depend on execution order.
    """
    async with current_engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # The same bootstrap the server runs: on Postgres that also enables
    # pgvector and creates the vector indexes, which create_all alone cannot.
    await bootstrap(current_engine())
    yield


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client for the FastAPI application."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def authed_client():
    """
    Client carrying a real signed session for a real member.

    Signs an actual cookie rather than overriding the dependency, so the
    session gate and member lookup are exercised the way production runs them.
    """
    import time
    import uuid

    from sqlalchemy import select

    from app.config import settings
    from app.database.connection import AsyncSessionLocal
    from app.middleware.auth_gate import COOKIE_NAME, SESSION_TTL_SECONDS, sign_session
    from app.models.database import User

    email = f"tester-{uuid.uuid4().hex[:8]}@example.com"
    async with AsyncSessionLocal() as session:
        user = User(
            organization_id=uuid.UUID(settings.DEFAULT_ORG_ID),
            email=email,
            name="Tester",
            is_active=True,
            settings={},
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    token = sign_session(str(user_id), int(time.time()) + SESSION_TTL_SECONDS)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", cookies={COOKIE_NAME: token}
    ) as c:
        c.user_id = user_id
        yield c
