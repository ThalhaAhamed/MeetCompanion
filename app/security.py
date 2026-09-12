"""
Password hashing.

Uses bcrypt directly rather than through passlib. passlib has been unmaintained
since 2020 and its bcrypt backend detection breaks against bcrypt 4.1+, which
surfaced as "no backends available" on a clean install - a failure a new
contributor would hit the first time they created an account.

Hashes are ordinary bcrypt ($2b$) strings, so credentials created by the
previous passlib-based code continue to verify unchanged.
"""
from __future__ import annotations

import bcrypt

#: bcrypt only considers the first 72 bytes of a password and raises on longer
#: input. Truncating matches what passlib did, so existing hashes still verify.
MAX_PASSWORD_BYTES = 72

DEFAULT_ROUNDS = 12


def _encode(password: str) -> bytes:
    return password.encode("utf-8")[:MAX_PASSWORD_BYTES]


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password must not be empty.")
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt(rounds=DEFAULT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time check that never raises on malformed stored hashes."""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(_encode(password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
