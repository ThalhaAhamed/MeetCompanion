"""
Per-member login. There's no self-serve signup - the very first member is
created via POST /api/members using the SHARED_PASSPHRASE as one-time proof
of ownership (see app/api/members.py); everyone after that is added by an
already-logged-in member from the Members page.
"""
import time
import uuid
from fastapi import APIRouter, HTTPException, Response, Request, Depends
from pydantic import BaseModel
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.connection import get_db
from app.models.database import User
from app.middleware.auth_gate import COOKIE_NAME, SESSION_TTL_SECONDS, sign_session, decode_session

router = APIRouter(prefix="/api/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email.strip().lower(), User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not pwd_context.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = sign_session(str(user.id), int(time.time()) + SESSION_TTL_SECONDS)
    # Frontend and backend live on different Railway subdomains, so this is a
    # cross-site request from the browser's point of view - SameSite=Lax
    # cookies are withheld from cross-site fetch/XHR, only None works here.
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="none",
        secure=True,
    )
    return {"authenticated": True, "member": {"id": str(user.id), "name": user.name, "email": user.email}}


@router.post("/logout")
async def logout(response: Response):
    # delete_cookie must be told the same SameSite/Secure attributes the
    # cookie was set with, or the browser treats it as a different cookie
    # and silently ignores the deletion.
    response.delete_cookie(COOKIE_NAME, samesite="none", secure=True)
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
    return {"authenticated": True, "member": {"id": str(user.id), "name": user.name, "email": user.email}}
