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
from app.secrets import configured_mcp_token

POSTGRESQL = "postgresql"

#: MCP tokens that were ever shipped as defaults. See app/secrets.py.
PLACEHOLDER_TOKENS = frozenset({"dev-mcp-token-meetstream-2026", "local-dev-token", "change-me-to-a-random-string"})


async def bootstrap(engine: AsyncEngine) -> None:
    """Schema first, then the rows every request depends on."""
    await ensure_schema(engine)
    await ensure_default_workspace(engine)
    await ensure_workspace_owners(engine)


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
        await _patch_action_items(conn, dialect)


async def _patch_action_items(conn, dialect: str) -> None:
    """
    Action items used to require a meeting; hand-written tasks in notes
    do not have one. Adds note_id and relaxes meeting_id on databases created
    before that change. create_all above already did this for new ones.
    """
    if dialect == POSTGRESQL:
        await conn.execute(text(
            "ALTER TABLE action_items ADD COLUMN IF NOT EXISTS note_id UUID REFERENCES notes(id) ON DELETE SET NULL"
        ))
        await conn.execute(text("ALTER TABLE action_items ALTER COLUMN meeting_id DROP NOT NULL"))
        return

    if dialect != "sqlite":
        return

    columns = {row[1]: row for row in (await conn.execute(text("PRAGMA table_info(action_items)"))).all()}
    if "note_id" not in columns:
        await conn.execute(text("ALTER TABLE action_items ADD COLUMN note_id CHAR(32) REFERENCES notes(id) ON DELETE SET NULL"))
        columns = {row[1]: row for row in (await conn.execute(text("PRAGMA table_info(action_items)"))).all()}
    # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
    if columns["meeting_id"][3]:
        # SQLite cannot drop NOT NULL in place: rebuild the table from the
        # current model and copy the rows across.
        table = Base.metadata.tables["action_items"]
        names = ", ".join(column.name for column in table.columns)
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.execute(text("ALTER TABLE action_items RENAME TO action_items__old"))
        # Indexes follow the renamed table and would collide with the ones
        # table.create() declares.
        for index in table.indexes:
            await conn.execute(text(f"DROP INDEX IF EXISTS {index.name}"))
        await conn.run_sync(lambda sync_conn: table.create(sync_conn))
        await conn.execute(text(f"INSERT INTO action_items ({names}) SELECT {names} FROM action_items__old"))
        await conn.execute(text("DROP TABLE action_items__old"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))


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
    explicit_token = configured_mcp_token()
    if explicit_token:
        await conn.execute(
            text(
                "UPDATE organizations SET mcp_token = :token "
                "WHERE id = :org_id AND mcp_token IS NULL"
            ),
            {"token": explicit_token, "org_id": settings.DEFAULT_ORG_ID},
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
                    mcp_token=configured_mcp_token() or secrets.token_urlsafe(32),
                    join_code=secrets.token_hex(4),
                )
            )
        else:
            # Older databases may predate these columns having values.
            if not existing.mcp_token:
                existing.mcp_token = configured_mcp_token() or secrets.token_urlsafe(32)
            elif existing.mcp_token in PLACEHOLDER_TOKENS:
                # Installs created before tokens were generated shipped with a
                # token that is public in this repository. Replace it; the
                # agent, if any, is re-wired on next activation.
                existing.mcp_token = secrets.token_urlsafe(32)
            if not existing.join_code:
                existing.join_code = secrets.token_hex(4)
        await session.commit()




async def ensure_workspace_owners(engine: AsyncEngine) -> None:
    """
    Every workspace has at least one owner.

    Roles predate this code: existing members are all "member". The earliest
    active member of each workspace without an owner becomes its owner, which
    is who created it in every realistic history.
    """
    from app.models.database import User

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        owned = {
            row[0]
            for row in (
                await session.execute(
                    select(User.organization_id).where(User.role == "owner", User.is_active.is_(True)).distinct()
                )
            ).all()
        }
        candidates = (
            await session.execute(
                select(User).where(User.is_active.is_(True)).order_by(User.organization_id, User.created_at)
            )
        ).scalars().all()
        changed = False
        for user in candidates:
            if user.organization_id in owned:
                continue
            user.role = "owner"
            owned.add(user.organization_id)
            changed = True
        if changed:
            await session.commit()
