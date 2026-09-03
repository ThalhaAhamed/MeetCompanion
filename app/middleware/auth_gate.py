"""
Shared-passphrase session gate.

Signs a plain "<expires_at>.<hmac>" cookie value using API_KEY_SALT as the
HMAC key - no session store needed since the only claim is "the passphrase
was entered before this timestamp". Enforced by AuthGateMiddleware on every
/api/* route except the auth routes themselves and webhooks (MeetStream, not
a browser, calls those) and the MCP endpoints (gated separately by their own
bearer token, called by the voice agent rather than a browser).
"""
import hmac
import hashlib
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.config import settings

COOKIE_NAME = "hub_session"
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days

EXEMPT_PREFIXES = ("/api/auth/", "/api/webhooks", "/mcp", "/health", "/docs", "/openapi.json", "/redoc")


def _key() -> bytes:
    return settings.API_KEY_SALT.encode("utf-8")


def sign_session(expires_at: int) -> str:
    payload = str(expires_at)
    mac = hmac.new(_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{mac}"


def verify_session(token: str) -> bool:
    try:
        payload, mac = token.rsplit(".", 1)
        expected = hmac.new(_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            return False
        return int(payload) > int(time.time())
    except (ValueError, AttributeError):
        return False


class AuthGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.SHARED_PASSPHRASE:
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/") or path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        if not token or not verify_session(token):
            return JSONResponse(status_code=401, content={"detail": "Passphrase required."})

        return await call_next(request)
