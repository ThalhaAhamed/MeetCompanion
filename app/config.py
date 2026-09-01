"""
Configuration management for MeetStream Companion.
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
    APP_NAME: str = "MeetStream Companion"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: List[str] = ["*"]

    # ---- Database ----
    DATABASE_URL: str = "postgresql+asyncpg://meetstream:meetstream_dev_password@localhost:5432/meetstream_companion"
    DATABASE_URL_SYNC: str = "postgresql://meetstream:meetstream_dev_password@localhost:5432/meetstream_companion"
    DEFAULT_ORG_ID: str = "00000000-0000-0000-0000-000000000001"

    # ---- MeetStream ----
    MEETSTREAM_API_KEY: Optional[str] = None
    MEETSTREAM_API_BASE_URL: str = "https://api.meetstream.ai"
    MEETSTREAM_WEBHOOK_SECRET: Optional[str] = None
    MEETSTREAM_AGENT_CONFIG_ID: Optional[str] = None

    # ---- MCP Server ----
    MCP_AUTH_TOKEN: str = "dev-mcp-token-meetstream-2026"
    MCP_SERVER_URL: str = "http://localhost:8000/mcp"

    # ---- LLM (Memory Extraction) ----
    LLM_PROVIDER: str = "openai"  # openai, groq, anthropic
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4.1"
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"

    # ---- Embeddings ----
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100

    # ---- Security ----
    API_KEY_SALT: str = "meetstream_companion_secure_salt_2026"


settings = Settings()
