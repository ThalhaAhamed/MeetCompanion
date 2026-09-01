"""
Pytest configuration and shared test fixtures.
"""
import pytest
import pytest_asyncio
import httpx
from unittest.mock import AsyncMock, MagicMock
from app.main import app
from app.config import settings


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client for FastAPI application."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
