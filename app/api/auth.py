"""
Shared-passphrase gate for the dashboard/API.

There are no user accounts in this app - everyone who knows the passphrase
gets the same shared view of all data (see AgentSettings/day-view). This
endpoint just exchanges a correct passphrase for a signed, expiring session
cookie; app.middleware.auth_gate enforces that cookie on every other /api
route.
"""
import hmac
import time
from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel
from app.config import settings
from app.middleware.auth_gate import COOKIE_NAME, SESSION_TTL_SECONDS, sign_session, verify_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    passphrase: str


@router.post("/login")
async def login(body: LoginRequest, response: Response):
    if not settings.SHARED_PASSPHRASE:
        raise HTTPException(status_code=400, detail="No shared passphrase is configured.")
    if not hmac.compare_digest(body.passphrase, settings.SHARED_PASSPHRASE):
        raise HTTPException(status_code=401, detail="Incorrect passphrase.")

    token = sign_session(int(time.time()) + SESSION_TTL_SECONDS)
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
    return {"authenticated": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"authenticated": False}


@router.get("/check")
async def check(request: Request):
    if not settings.SHARED_PASSPHRASE:
        return {"authenticated": True, "gate_enabled": False}
    token = request.cookies.get(COOKIE_NAME)
    return {"authenticated": bool(token and verify_session(token)), "gate_enabled": True}
