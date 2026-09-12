"""
Database connection and session management.

Engine construction is dialect-aware: SQLite and Postgres need different
pooling and connection arguments, and SQLite additionally needs foreign key
enforcement turned on explicitly.
"""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.runtime_config import is_env_managed, load_config

SQLITE = "sqlite"
POSTGRESQL = "postgresql"


def normalize_database_url(url: str) -> str:
    """
    Ensure the URL names an async driver.

    Users naturally write `sqlite:///app.db` or `postgresql://...` from other
    tooling; both are silently upgraded rather than failing with an opaque
    "does not support async" error.
    """
    if url.startswith("sqlite+"):
        return url
    if url.startswith("sqlite:"):
        return url.replace("sqlite:", "sqlite+aiosqlite:", 1)
    if url.startswith("postgresql+"):
        return url
    if url.startswith(("postgresql:", "postgres:")):
        scheme, _, rest = url.partition(":")
        return f"postgresql+asyncpg:{rest}"
    return url


def dialect_of(url: str) -> str:
    if url.startswith(SQLITE):
        return SQLITE
    if url.startswith(("postgresql", "postgres")):
        return POSTGRESQL
    return url.split(":", 1)[0]


def _sqlite_file_path(url: str) -> str:
    path = url.split(":///", 1)[-1].split("?", 1)[0]
    return path


def _engine_options(url: str) -> Dict[str, Any]:
    options: Dict[str, Any] = {
        "echo": settings.LOG_LEVEL.upper() == "DEBUG",
        "future": True,
    }

    if dialect_of(url) == SQLITE:
        # SQLite has no server to pool against, and the default pool arguments
        # below are rejected outright by its dialect.
        file_path = _sqlite_file_path(url)
        if file_path and file_path != ":memory:":
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        return options

    options.update(pool_pre_ping=True, pool_size=10, max_overflow=20)
    return options


def resolve_database_url() -> str:
    """
    Explicit environment (or .env) first, then the URL saved from the UI,
    then the SQLite default - the same precedence as every other setting.
    """
    if is_env_managed("DATABASE_URL"):
        return normalize_database_url(settings.DATABASE_URL)
    stored = load_config().database.url
    if stored:
        return normalize_database_url(stored)
    return normalize_database_url(settings.DATABASE_URL)


DATABASE_URL = resolve_database_url()
DIALECT = dialect_of(DATABASE_URL)

engine = create_async_engine(DATABASE_URL, **_engine_options(DATABASE_URL))

if DIALECT == SQLITE:

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        # SQLite ignores foreign keys unless asked, which would let the
        # ON DELETE CASCADE rules the schema relies on silently do nothing.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI endpoints to acquire a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for background workers to acquire a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
