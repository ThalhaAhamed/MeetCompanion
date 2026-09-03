"""
Shared request-scoped dependencies: resolving the signed-in member and their
workspace (organization) from the session cookie. Every org-scoped endpoint
should depend on get_current_org_id instead of hardcoding a default org, so
each workspace only ever sees its own data.
"""
import uuid
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_db
from app.models.database import User
from app.middleware.auth_gate import COOKIE_NAME, decode_session


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    user_id = decode_session(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in required.")
    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return user


async def get_current_org_id(user: User = Depends(get_current_user)) -> uuid.UUID:
    return user.organization_id
