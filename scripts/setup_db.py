"""
Database setup and migration initialization script.
Connects to PostgreSQL, ensures pgvector extension is created, and runs 001_initial_schema.sql.
"""
import asyncio
import os
import sys
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings


async def init_db():
    print(f"[SETUP] Connecting to database at {settings.DATABASE_URL.split('@')[-1]}...")
    # echo=True previously dumped the full SQL text of every one of the ~50
    # migration statements on every single container boot (this script reruns
    # each time as an idempotency check) - on Railway that alone blew past
    # their 500 logs/sec rate limit, silently dropping real log lines
    # (including uvicorn's own startup line) right when they mattered most
    # for debugging a boot failure.
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    # This script reruns on every container boot (the Docker image runs it
    # before starting uvicorn), so skip entirely once the schema is already
    # in place instead of re-attempting and warning on ~50 statements - a
    # real problem on platforms with per-second log rate limits, and just
    # slower everywhere else.
    async with engine.connect() as conn:
        already_migrated = (
            await conn.execute(text("SELECT to_regclass('public.organizations')"))
        ).scalar() is not None
    if already_migrated:
        print("[SETUP] Schema already present - skipping migration.")
        await engine.dispose()
        return

    schema_file = PROJECT_ROOT / "migrations" / "001_initial_schema.sql"
    if not schema_file.exists():
        print(f"[ERROR] Schema file not found at {schema_file}")
        return

    with open(schema_file, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    print("[SETUP] Executing initial schema migration...")
    statements = [stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()]
    for stmt in statements:
        # Each statement gets its own transaction. A single shared transaction
        # (the previous behavior) meant one "already exists" error on a rerun
        # (this script runs on every container boot so it's idempotent for
        # fresh databases) would poison the whole transaction, turning every
        # statement after the first failure into a cascading
        # InFailedSqlTransactionError even though nothing was actually wrong
        # with them.
        try:
            async with engine.begin() as conn:
                await conn.execute(text(stmt))
        except Exception as e:
            # Genuinely expected on a rerun: tables/indexes/extensions that
            # already exist from a previous boot. str(e) on a SQLAlchemy
            # StatementError includes the full SQL text of the failing
            # statement - printing just the wrapped driver exception keeps
            # this from re-adding the same log-volume problem echo=True had.
            print(f"[WARN] {getattr(e, 'orig', e)}")

    await engine.dispose()
    print("[SETUP] Database initialization completed successfully!")


if __name__ == "__main__":
    asyncio.run(init_db())
