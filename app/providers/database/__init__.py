"""
Database provider selection.

The backend is chosen from the live connection's dialect rather than from
configuration, so pointing DATABASE_URL at a different database is the only
step required to switch - nothing has to be kept in sync by hand.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.database.base import ScoredRow, SearchBackend
from app.providers.database.portable import PortableSearchBackend
from app.providers.database.postgres import PostgresSearchBackend

__all__ = [
    "ScoredRow",
    "SearchBackend",
    "PortableSearchBackend",
    "PostgresSearchBackend",
    "get_search_backend",
    "describe_databases",
]


def get_search_backend(session: AsyncSession) -> SearchBackend:
    """The search backend matching the session's database dialect."""
    if session.bind.dialect.name == "postgresql":
        return PostgresSearchBackend(session)
    return PortableSearchBackend(session)


def describe_databases() -> list[dict]:
    """Serializable database options for the onboarding and settings forms."""
    return [
        {
            "name": "sqlite",
            "label": "Local SQLite",
            "summary": "Simple. No additional setup required - everything lives in one file on this machine.",
            "local": True,
            "recommended": True,
            "fields": [
                {
                    "key": "path",
                    "label": "Database file",
                    "type": "text",
                    "required": False,
                    "default": "data/meet-companion.db",
                    "help": "Relative paths are resolved against the project directory.",
                }
            ],
        },
        {
            "name": "postgresql",
            "label": "PostgreSQL",
            "summary": "Use an external PostgreSQL server. Requires the pgvector extension for similarity search.",
            "local": False,
            "recommended": False,
            "fields": [
                {
                    "key": "url",
                    "label": "Connection URL",
                    "type": "text",
                    "required": True,
                    "placeholder": "postgresql+asyncpg://user:password@localhost:5432/meet_companion",
                    "help": "Credentials are stored in your local configuration and never leave this machine.",
                }
            ],
        },
    ]
