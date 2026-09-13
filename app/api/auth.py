"""
Per-member login. Accounts are created through app/api/members.py - either
self-signup into a new or joined workspace, or added by an existing member.
"""
import time
import uuid
from fastapi import APIRouter, HTTPException, Response, Request, Depends

from app.config import settings
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_db
from app.models.database import User
from app.middleware.auth_gate import COOKIE_NAME, SESSION_TTL_SECONDS, sign_session, decode_session
from app.security import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def is_https(request: Request) -> bool:
    """Whether the browser reached us over TLS, looking through a trusted proxy."""
    if settings.TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-proto")
        if forwarded:
            return forwarded.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


def cookie_flags(request: Request) -> dict:
    """
    Session cookie attributes that actually work for how this install is reached.

    Over HTTPS the UI may live on another origin (a separately hosted
    frontend), which needs SameSite=None - and that attribute is only
    accepted together with Secure. Over plain HTTP - a LAN box, a NAS, the
    desktop bundle on 127.0.0.1 - a Secure cookie is silently dropped by the
    browser and nobody can stay signed in, so the cookie is SameSite=Lax
    instead: right for every same-origin deployment, and a cross-site
    deployment without TLS is not something to support.
    """
    if is_https(request):
        return {"samesite": "none", "secure": True}
    return {"samesite": "lax", "secure": False}


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email.strip().lower(), User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = sign_session(str(user.id), int(time.time()) + SESSION_TTL_SECONDS)
    response.set_cookie(key=COOKIE_NAME, value=token, max_age=SESSION_TTL_SECONDS, httponly=True, **cookie_flags(request))
    return {"authenticated": True, "member": {"id": str(user.id), "name": user.name, "email": user.email, "role": user.role}}


@router.post("/logout")
async def logout(request: Request, response: Response):
    # delete_cookie must be told the same SameSite/Secure attributes the
    # cookie was set with, or the browser treats it as a different cookie
    # and silently ignores the deletion.
    response.delete_cookie(COOKIE_NAME, **cookie_flags(request))
    return {"authenticated": False}


@router.get("/check")
async def check(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    user_id = decode_session(token) if token else None
    if not user_id:
        return {"authenticated": False}

    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "member": {"id": str(user.id), "name": user.name, "email": user.email, "role": user.role}}
