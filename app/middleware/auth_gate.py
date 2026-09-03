"""
Per-member session gate.

Signs a "<expires_at>.<user_id>.<hmac>" cookie value using API_KEY_SALT as the
HMAC key - the signature only proves the token was issued by us and hasn't
expired; membership itself (has this user_id been removed?) is re-checked
against the database on every request, so removing a member in the Members
page revokes their live session immediately rather than waiting for the
cookie to expire.

Enforced by AuthGateMiddleware on every /api/* route except the auth/member
routes themselves (which do their own checks), webhooks (MeetStream calls
those, not a browser), and the MCP endpoints (gated separately by their own
bearer token, called by the voice agent rather than a browser).
"""
import hmac
import hashlib
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy import select
from app.config import settings

COOKIE_NAME = "hub_session"
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days

EXEMPT_PREFIXES = ("/api/auth/", "/api/members", "/api/agent/chat-relay", "/api/webhooks", "/mcp", "/health", "/docs", "/openapi.json", "/redoc")


def _key() -> bytes:
    return settings.API_KEY_SALT.encode("utf-8")


def sign_session(user_id: str, expires_at: int) -> str:
    payload = f"{expires_at}.{user_id}"
    mac = hmac.new(_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{mac}"


def decode_session(token: str) -> "uuid.UUID | None":
    """Verify signature + expiry only (no DB hit) - returns the user_id or None."""
    try:
        expires_at, user_id, mac = token.split(".", 2)
        payload = f"{expires_at}.{user_id}"
        expected = hmac.new(_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            return None
        if int(expires_at) <= int(time.time()):
            return None
        return uuid.UUID(user_id)
    except (ValueError, AttributeError):
        return None


async def verify_session(token: str) -> bool:
    """Full check: valid signature/expiry AND the member still exists and is active."""
    user_id = decode_session(token)
    if not user_id:
        return False
    from app.database.connection import get_db_context
    from app.models.database import User

    async with get_db_context() as db:
        result = await db.execute(select(User.id).where(User.id == user_id, User.is_active.is_(True)))
        return result.scalar_one_or_none() is not None


class AuthGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        if not token or not await verify_session(token):
            return JSONResponse(status_code=401, content={"detail": "Sign in required."})

        return await call_next(request)
