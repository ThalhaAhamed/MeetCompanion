"""
Per-member session gate.

Signs a "<expires_at>.<user_id>.<hmac>" cookie value using the per-install
session secret (app/secrets.py) as the HMAC key - the signature only proves the token was issued by us and hasn't
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
from app.secrets import session_secret

COOKIE_NAME = "hub_session"
#: Set by the desktop shell before it loads the UI, never by the page itself.
DEVICE_COOKIE_NAME = "mc_device"
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days

EXEMPT_PREFIXES = ("/api/auth/", "/api/members", "/api/agent/chat-relay", "/api/webhooks", "/mcp", "/health", "/docs", "/openapi.json", "/redoc")

#: Setup runs before any account exists, so it cannot require a session - but
#: only until the application is configured. Leaving it open afterwards would
#: let anyone reachable on the network read configuration or reset the install.
FIRST_RUN_PREFIXES = ("/api/setup",)


def _key() -> bytes:
    return session_secret().encode("utf-8")


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

        if path.startswith(FIRST_RUN_PREFIXES):
            from app.runtime_config import is_configured

            if not is_configured():
                return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        if token and await verify_session(token):
            return await call_next(request)

        # No session: the desktop app on this machine may present the device
        # key instead, which signs the owner in rather than waving the request
        # through - everything downstream still sees a normal session.
        issued = await _session_from_device_key(request)
        if issued is not None:
            session_token, _user_id = issued
            # Put it on the *request* as well, not just the response: the
            # endpoints' own get_current_user dependency reads the cookie
            # header, so without this the gate would pass and the route would
            # still answer 401.
            _inject_session_cookie(request, session_token)
            response = await call_next(request)
            set_session_cookie(response, session_token, request)
            return response

        return JSONResponse(status_code=401, content={"detail": "Sign in required."})


def _inject_session_cookie(request: Request, token: str) -> None:
    """Make the rest of the stack see an ordinary signed-in request."""
    headers = [(k, v) for k, v in request.scope["headers"] if k.lower() != b"cookie"]
    existing = request.headers.get("cookie")
    merged = f"{existing}; {COOKIE_NAME}={token}" if existing else f"{COOKIE_NAME}={token}"
    headers.append((b"cookie", merged.encode("latin-1")))
    request.scope["headers"] = headers
    # starlette caches the parsed cookies on first access.
    request._cookies = None
    if "cookies" in request.__dict__:
        del request.__dict__["cookies"]


def set_session_cookie(response, token: str, request: Request) -> None:
    """Same attributes the login endpoint uses, so the two are indistinguishable."""
    from app.api.auth import cookie_flags

    response.set_cookie(
        key=COOKIE_NAME, value=token, max_age=SESSION_TTL_SECONDS, httponly=True,
        **cookie_flags(request),
    )


async def _session_from_device_key(request: Request):
    """
    Turn a valid device key into a session for the sole owner.

    Deliberately only when there is exactly one owner: on a shared workspace
    "the local user" is ambiguous, and silently picking one of several people
    would be both wrong and a way to inherit someone else's role.
    """
    import hmac as _hmac
    import time as _time

    presented = request.cookies.get(DEVICE_COOKIE_NAME)
    if not presented:
        return None

    from app.secrets import device_secret

    if not _hmac.compare_digest(presented, device_secret()):
        return None

    from app.database.connection import get_db_context
    from app.models.database import User

    async with get_db_context() as db:
        owners = (
            await db.execute(
                select(User.id).where(User.role == "owner", User.is_active.is_(True)).limit(2)
            )
        ).scalars().all()
    if len(owners) != 1:
        return None

    user_id = owners[0]
    return sign_session(str(user_id), int(_time.time()) + SESSION_TTL_SECONDS), user_id
