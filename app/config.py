"""
Configuration management for Meet Companion.
Loads settings from environment variables and .env file.
"""
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # ---- Application ----
    APP_NAME: str = "Meet Companion"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: List[str] = ["*"]

    # ---- Database ----
    # Local SQLite by default so the application runs with no external
    # services. Point this at postgresql+asyncpg://... to use Postgres, which
    # additionally enables pgvector-backed similarity search.
    DATABASE_URL: str = "sqlite+aiosqlite:///data/meet-companion.db"
    DEFAULT_ORG_ID: str = "00000000-0000-0000-0000-000000000001"

    # ---- MeetStream ----
    MEETSTREAM_API_KEY: Optional[str] = None
    MEETSTREAM_API_BASE_URL: str = "https://api.meetstream.ai"
    MEETSTREAM_WEBHOOK_SECRET: Optional[str] = None
    MEETSTREAM_AGENT_CONFIG_ID: Optional[str] = None

    # ---- MCP Server ----
    MCP_AUTH_TOKEN: str = "dev-mcp-token-meetstream-2026"
    MCP_SERVER_URL: str = "http://localhost:8000/mcp"

    # ---- LLM ----
    # Provider-agnostic configuration: one set of variables works for every
    # supported provider (see app/providers/llm). Anything left unset falls
    # back to that provider's documented default.
    LLM_PROVIDER: str = "ollama"  # openai, anthropic, gemini, ollama, groq, openai_compatible
    LLM_MODEL: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: Optional[int] = None

    # Legacy per-provider names, still honoured so an existing .env keeps
    # working. Prefer the LLM_* variables above for new setups.
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: Optional[str] = None

    # ---- Embeddings ----
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100

    # ---- Security ----
    API_KEY_SALT: str = "meet_companion_secure_salt_2026"


settings = Settings()
