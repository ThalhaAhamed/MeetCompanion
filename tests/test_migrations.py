"""
Alembic wiring: the baseline builds the schema, adoption stamps an existing
pre-Alembic database, and the models have not drifted from the baseline.
"""
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.database.bootstrap import BASELINE_REVISION, ensure_schema
from app.models.database import Base

APP_TABLES = set(Base.metadata.tables)


def _fresh_url() -> str:
    path = Path(tempfile.mkdtemp()) / f"mig-{uuid.uuid4().hex}.db"
    return f"sqlite+aiosqlite:///{path.as_posix()}"


async def _tables(engine) -> set:
    async with engine.connect() as conn:
        return set(await conn.run_sync(lambda c: inspect(c).get_table_names()))


async def _version(engine) -> str | None:
    async with engine.connect() as conn:
        if not await conn.run_sync(lambda c: inspect(c).has_table("alembic_version")):
            return None
        return (await conn.execute(text("select version_num from alembic_version"))).scalar()


@pytest.mark.asyncio
async def test_fresh_database_is_migrated_to_head():
    engine = create_async_engine(_fresh_url())
    try:
        await ensure_schema(engine)
        tables = await _tables(engine)
        assert APP_TABLES <= tables, APP_TABLES - tables
        assert await _version(engine) == BASELINE_REVISION
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_existing_prealembic_database_is_adopted_not_rebuilt():
    engine = create_async_engine(_fresh_url())
    try:
        # Simulate a pre-Alembic install: schema exists, no alembic_version.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        assert await _version(engine) is None
        await ensure_schema(engine)
        assert await _version(engine) == BASELINE_REVISION  # stamped, not re-run
        assert APP_TABLES <= await _tables(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dropped_tables_under_stale_version_are_rebuilt():
    engine = create_async_engine(_fresh_url())
    try:
        await ensure_schema(engine)  # now at head
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)  # leaves alembic_version
        await ensure_schema(engine)  # must notice tables gone and rebuild
        assert APP_TABLES <= await _tables(engine)
        assert await _version(engine) == BASELINE_REVISION
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_models_have_not_drifted_from_the_baseline():
    """
    Autogenerate against a database at head must find nothing to do; a real
    schema change would show up here and remind the author to add a revision.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    engine = create_async_engine(_fresh_url())
    try:
        await ensure_schema(engine)
        async with engine.connect() as conn:
            def _compare(sync_conn):
                ctx = MigrationContext.configure(
                    sync_conn,
                    opts={"compare_type": True, "target_metadata": Base.metadata},
                )
                return compare_metadata(ctx, Base.metadata)
            diff = await conn.run_sync(_compare)
    finally:
        await engine.dispose()
    # On SQLite the diff should be empty (pgvector HNSW indexes never appear here).
    assert diff == [], f"models drifted from baseline; add a migration: {diff}"
