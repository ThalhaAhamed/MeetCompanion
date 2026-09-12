"""
Setup and configuration endpoints.

Backs the first-run onboarding flow and the Settings screen. Secrets are
accepted here but never returned: responses carry masked previews only.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.database.connection import current_url, dialect_of, normalize_database_url, switch_database
from app.providers.database import build_database_url, describe_databases, provider_for_url
from app.providers.llm import (
    DESCRIPTORS,
    LLMConfig,
    LLMConfigError,
    create_llm_provider,
    describe_providers,
)
from app.runtime_config import (
    DatabaseSettings,
    LLMSettings,
    MeetStreamSettings,
    describe_environment_managed,
    is_configured,
    is_env_managed,
    load_config,
    mask_secret,
    reset_config,
    update_config,
)
from app.services.llm import build_llm_config

router = APIRouter(prefix="/api/setup", tags=["setup"])


class LLMConfigPayload(BaseModel):
    provider: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)


class DatabaseConfigPayload(BaseModel):
    """Either a provider with its form values, or a ready-made URL."""
    provider: Optional[str] = None
    values: Optional[Dict[str, Any]] = None
    url: Optional[str] = None

    def resolve_url(self) -> Optional[str]:
        if self.provider:
            try:
                return build_database_url(self.provider, self.values)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        if self.url:
            return normalize_database_url(self.url)
        return None


class MeetStreamConfigPayload(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class CompleteSetupPayload(BaseModel):
    llm: Optional[LLMConfigPayload] = None
    database: Optional[DatabaseConfigPayload] = None
    meetstream: Optional[MeetStreamConfigPayload] = None


@router.get("/status")
async def setup_status() -> Dict[str, Any]:
    """Whether onboarding is needed, and what the effective configuration is."""
    config = load_config()

    try:
        active = build_llm_config()
        llm_summary: Dict[str, Any] = {
            "provider": active.provider,
            "model": active.model,
            "base_url": active.base_url,
            "api_key": mask_secret(active.api_key),
            "configured": True,
        }
    except LLMConfigError as exc:
        llm_summary = {"configured": False, "error": str(exc)}

    return {
        "onboarding_completed": config.onboarding_completed,
        "needs_setup": not is_configured(),
        "environment_managed": describe_environment_managed(),
        "llm": llm_summary,
        "database": {
            "dialect": dialect_of(current_url()),
            "provider": provider_for_url(current_url()),
            "url": mask_secret(current_url()),
        },
        "meetstream": {
            "configured": bool(config.meetstream.api_key or settings.MEETSTREAM_API_KEY),
            "api_key": mask_secret(config.meetstream.api_key or settings.MEETSTREAM_API_KEY),
        },
    }


@router.get("/providers")
async def list_providers() -> Dict[str, Any]:
    """Everything the onboarding and settings forms need to render themselves."""
    return {"llm": describe_providers(), "databases": describe_databases()}


@router.post("/test-llm")
async def test_llm(payload: LLMConfigPayload) -> Dict[str, Any]:
    """
    Verify a provider configuration without saving it.

    Lets onboarding tell the user their key or host is wrong before they
    commit to it, rather than failing later during meeting processing.
    """
    descriptor = DESCRIPTORS.get(payload.provider)
    if descriptor is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider '{payload.provider}'.",
        )

    try:
        provider = create_llm_provider(
            LLMConfig(
                provider=payload.provider,
                model=payload.model or "",
                api_key=payload.api_key,
                base_url=payload.base_url,
                temperature=payload.temperature if payload.temperature is not None else 0.2,
                max_tokens=payload.max_tokens,
            )
        )
    except LLMConfigError as exc:
        return {"ok": False, "detail": str(exc), "models": []}

    result = await provider.health_check()
    return {"ok": result.ok, "detail": result.detail, "models": result.models}


@router.post("/test-database")
async def test_database(payload: DatabaseConfigPayload) -> Dict[str, Any]:
    """Verify a database is reachable before it is saved."""
    url = payload.resolve_url()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="A database URL is required."
        )
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = None
    try:
        # A wrong host should fail fast, not leave the form spinning until
        # the OS gives up on the socket.
        connect_args = {"timeout": 5} if dialect_of(url) == "postgresql" else {}
        engine = create_async_engine(url, connect_args=connect_args)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"ok": True, "detail": "Connected.", "dialect": dialect_of(url)}
    except Exception as exc:
        return {"ok": False, "detail": str(exc), "dialect": dialect_of(url)}
    finally:
        if engine is not None:
            await engine.dispose()


@router.post("/complete")
async def complete_setup(payload: CompleteSetupPayload) -> Dict[str, Any]:
    """Persist the chosen configuration and leave first-run onboarding."""
    current = load_config()

    llm = current.llm
    if payload.llm is not None:
        if payload.llm.provider not in DESCRIPTORS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown provider '{payload.llm.provider}'.",
            )
        llm = LLMSettings(
            provider=payload.llm.provider,
            model=payload.llm.model,
            # An omitted key keeps the stored one, so re-saving settings does
            # not wipe a secret the form never displayed back to the user.
            api_key=payload.llm.api_key if payload.llm.api_key is not None else current.llm.api_key,
            base_url=payload.llm.base_url,
            temperature=payload.llm.temperature,
            max_tokens=payload.llm.max_tokens,
        )

    database = current.database
    if payload.database is not None:
        resolved = payload.database.resolve_url()
        if resolved:
            if is_env_managed("DATABASE_URL"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="DATABASE_URL is set in the environment; change it there.",
                )
            # Switched before anything is saved: a database that cannot be
            # reached or prepared must not end up in the config either.
            try:
                await switch_database(resolved)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Could not switch database: {exc}",
                )
            database = DatabaseSettings(url=resolved)

    meetstream = current.meetstream
    if payload.meetstream is not None:
        meetstream = MeetStreamSettings(
            api_key=payload.meetstream.api_key
            if payload.meetstream.api_key is not None
            else current.meetstream.api_key,
            base_url=payload.meetstream.base_url or current.meetstream.base_url,
        )

    update_config(
        onboarding_completed=True,
        llm=llm,
        database=database,
        meetstream=meetstream,
    )
    return await setup_status()


@router.post("/reset")
async def reset_setup() -> Dict[str, Any]:
    """Forget stored configuration and return to first-run onboarding."""
    reset_config()
    return await setup_status()
