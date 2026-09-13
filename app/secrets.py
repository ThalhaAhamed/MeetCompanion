"""
Instance secrets that must never come from a default.

The session signing key used to be `API_KEY_SALT` with a hard-coded default,
which meant every install that did not set it shared one key - and anyone who
read the repository could mint a session cookie for any user id. The key is
now generated once per install and kept next to the database, unless the
deployment provides one explicitly through the environment.

Known placeholder values (from older .env.example files and dev scripts) are
treated as unset so a copied example file cannot silently downgrade security.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Optional

#: Values that have appeared in this project's examples or defaults. Never
#: accepted as real secrets.
KNOWN_PLACEHOLDERS = frozenset(
    {
        "meet_companion_secure_salt_2026",
        "dev-mcp-token-meetstream-2026",
        "local-dev-token",
        "change-me-to-a-random-string",
        "change-me",
        "changeme",
        "secret",
        "password",
    }
)

MIN_SECRET_LENGTH = 16


def is_placeholder(value: Optional[str]) -> bool:
    """True for empty, too-short, or well-known example values."""
    if not value:
        return True
    stripped = value.strip()
    return len(stripped) < MIN_SECRET_LENGTH or stripped.lower() in KNOWN_PLACEHOLDERS


def _data_dir() -> Path:
    """Where per-install state lives - the same directory as config.json."""
    configured = os.environ.get("MEET_COMPANION_CONFIG")
    if configured:
        return Path(configured).parent
    return Path("data")


def _file_secret(name: str) -> str:
    """Read a secret from <data>/<name>, generating it on first use."""
    path = _data_dir() / name
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if not is_placeholder(existing):
            return existing
    except OSError:
        pass

    value = secrets.token_urlsafe(48)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value


_session_secret: Optional[str] = None


def session_secret() -> str:
    """
    The HMAC key for session cookies.

    Precedence: SESSION_SECRET, then the legacy API_KEY_SALT name (so an
    existing deployment's sessions keep working), then a generated key stored
    in the data directory. Placeholder values are ignored.
    """
    global _session_secret
    if _session_secret is None:
        for name in ("SESSION_SECRET", "API_KEY_SALT"):
            value = os.environ.get(name)
            if not is_placeholder(value):
                _session_secret = value.strip()
                break
        else:
            _session_secret = _file_secret("session.key")
    return _session_secret


def configured_mcp_token() -> Optional[str]:
    """
    An MCP bearer token supplied explicitly by the deployment, or None.

    Used only to keep an existing default workspace's already-wired agent
    working. New workspaces always get a random token.
    """
    value = os.environ.get("MCP_AUTH_TOKEN")
    return None if is_placeholder(value) else value.strip()


def reset_for_tests() -> None:
    global _session_secret
    _session_secret = None
