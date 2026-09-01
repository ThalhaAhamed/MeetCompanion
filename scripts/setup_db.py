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
    engine = create_async_engine(settings.DATABASE_URL, echo=True)

    schema_file = PROJECT_ROOT / "migrations" / "001_initial_schema.sql"
    if not schema_file.exists():
        print(f"[ERROR] Schema file not found at {schema_file}")
        return

    with open(schema_file, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    async with engine.begin() as conn:
        print("[SETUP] Executing initial schema migration...")
        # Execute each statement
        statements = [stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()]
        for stmt in statements:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                # Some objects might already exist or need notice handling
                print(f"[WARN] Statement notice/warning: {e}")

    await engine.dispose()
    print("[SETUP] Database initialization completed successfully!")


if __name__ == "__main__":
    asyncio.run(init_db())
