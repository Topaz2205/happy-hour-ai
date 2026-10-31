"""
Password hashing and access tokens.

Passwords: scrypt from the standard library (memory-hard, no native extension
to build on the host). Stored as  scrypt$n$r$p$<salt b64>$<hash b64>  so the
cost parameters can be raised later without invalidating existing hashes.

Tokens: HS256 JWTs signed with AUTH_SECRET_KEY, carrying only the user id. The
workspace is never read from the token or from any client field — it is
resolved from memberships in the database on every request.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings

log = logging.getLogger("happyhour.security")

_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 64
_ALGORITHM = "HS256"
_ISSUER = "happy-hour-ai"

_ephemeral_secret: str | None = None


def _secret() -> str:
    """The signing key. Refuses to run in production without a real one."""
    global _ephemeral_secret
    if settings.AUTH_SECRET_KEY:
        if settings.is_production and len(settings.AUTH_SECRET_KEY) < 32:
            raise RuntimeError("AUTH_SECRET_KEY must be at least 32 characters in production.")
        return settings.AUTH_SECRET_KEY
    if settings.is_production:
        raise RuntimeError("AUTH_SECRET_KEY is not set. Refusing to issue tokens in production.")
    if _ephemeral_secret is None:
        _ephemeral_secret = secrets.token_urlsafe(48)
        log.warning("AUTH_SECRET_KEY not set — using a random per-process key. "
                    "Tokens will stop working when the API restarts.")
    return _ephemeral_secret


def validate_security_settings() -> None:
    """Called at startup so a misconfigured production API fails loudly."""
    _secret()


# ── Passwords ────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                                n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


# Used when the email is unknown, so a failed login costs the same time either
# way and response timing does not reveal which emails have accounts.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


# ── Tokens ───────────────────────────────────────────────────────────────────

def create_access_token(user_id: uuid.UUID) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=settings.AUTH_TOKEN_TTL_HOURS)
    token = jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": expires, "iss": _ISSUER, "typ": "access"},
        _secret(), algorithm=_ALGORITHM,
    )
    return token, expires


def decode_access_token(token: str) -> uuid.UUID | None:
    """The user id in a valid token, or None for anything invalid or expired."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=[_ALGORITHM],
                            issuer=_ISSUER, options={"require": ["sub", "exp", "iat"]})
        if claims.get("typ") != "access":
            return None
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None
