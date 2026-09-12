"""
Bring a database up to date and ready for first use.

Runs at startup and again whenever the database is switched from Settings,
so the same code path serves a brand new SQLite file, an existing Postgres
deployment and a freshly pasted Supabase URL.
"""
from __future__ import annotations

import secrets
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import settings
from app.models.database import Base

POSTGRESQL = "postgresql"


async def bootstrap(engine: AsyncEngine) -> None:
    """Schema first, then the rows every request depends on."""
    await ensure_schema(engine)
    await ensure_default_workspace(engine)


async def ensure_schema(engine: AsyncEngine) -> None:
    """
    Bring the database up to date at startup.

    Creating the schema from the ORM metadata means a brand new database - in
    particular a local SQLite file - needs no migration step, no psql session
    and no setup script; the application simply works on first run.

    Existing Postgres deployments predate several columns, so they additionally
    get the idempotent patches below.
    """
    dialect = engine.dialect.name
    async with engine.begin() as conn:
        if dialect == POSTGRESQL:
            # The vector column type cannot be created until the extension is.
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        await conn.run_sync(Base.metadata.create_all)

        if dialect == POSTGRESQL:
            await _create_postgres_vector_indexes(conn)
            await _patch_legacy_postgres_schema(conn)


async def _create_postgres_vector_indexes(conn):
    """
    Create the ivfflat indexes that back similarity search on Postgres.

    These cannot be declared on the ORM models because the index type only
    exists in pgvector; the portable backend needs no index at all.
    """
    for table in ("meeting_memory_embeddings", "company_knowledge_embeddings"):
        await conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_embedding "
                f"ON {table} USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
            )
        )


async def _patch_legacy_postgres_schema(conn):
    """
    Additive patches for Postgres databases created before these columns
    existed. Guarded with IF NOT EXISTS so they are safe to re-run, and skipped
    entirely on databases created from current metadata.
    """
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
    # One-time cleanup: member removal used to set is_active=FALSE instead
    # of deleting the row (fixed in app/api/members.py), so a removed
    # member's email stayed permanently reserved by the (organization_id,
    # email) constraint - "that email is already a member" for an email
    # nobody could actually sign back in with. Removal deletes the row now,
    # so this only ever needs to run once for rows soft-deleted before
    # that fix.
    await conn.execute(text("DELETE FROM users WHERE is_active = FALSE"))

    await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS settings JSONB DEFAULT '{}'::jsonb"))
    # Tracks which member's own MeetStream API key (and account) a bot was
    # actually deployed under, so status/stop calls on that bot later use
    # the same key it was created with - necessary now that each member
    # can configure their own key (see app/api/agent.py get_meetstream_api_key),
    # since a bot created under one member's MeetStream account can only
    # be queried/stopped with that same account's key, not another
    # member's. Existing rows stay NULL (falls back to the deployment's
    # shared default key, same as before this column existed).
    await conn.execute(text("ALTER TABLE meetings ADD COLUMN IF NOT EXISTS created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL"))
    # Agent ownership/activation moved from the shared workspace to each
    # individual member - meeting memory stays workspace-shared, but who
    # you're talking to as "your agent" doesn't. Backfill: members of the
    # original default workspace inherit whatever agent the workspace had
    # active before this change, as their own personal starting point,
    # rather than suddenly having no agent configured at all.
    await conn.execute(
        text(
            """
            UPDATE users u
            SET settings = jsonb_build_object(
                'active_agent_config_id', o.settings->'active_agent_config_id',
                'agent_config_ids', COALESCE(o.settings->'agent_config_ids', '[]'::jsonb)
            )
            FROM organizations o
            WHERE u.organization_id = o.id
              AND u.organization_id = :org_id
              AND NOT (u.settings ? 'active_agent_config_id')
            """
        ),
        {"org_id": settings.DEFAULT_ORG_ID},
    )


async def ensure_default_workspace(engine: AsyncEngine) -> None:
    """
    Guarantee the default workspace exists.

    A fresh install - a new SQLite file in particular - has no rows at all, and
    every request resolves through an organization. Creating it here is what
    lets the application come up usable on first run without a seeding script.
    """
    from app.models.database import Organization

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        org_id = uuid.UUID(settings.DEFAULT_ORG_ID)
        existing = (
            await session.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                Organization(
                    id=org_id,
                    name="My Workspace",
                    slug="default",
                    settings={},
                    mcp_token=settings.MCP_AUTH_TOKEN or secrets.token_urlsafe(32),
                    join_code=secrets.token_hex(4),
                )
            )
        else:
            # Older databases may predate these columns having values.
            if not existing.mcp_token and settings.MCP_AUTH_TOKEN:
                existing.mcp_token = settings.MCP_AUTH_TOKEN
            if not existing.join_code:
                existing.join_code = secrets.token_hex(4)
        await session.commit()


