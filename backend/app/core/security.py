import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings
from app.core.errors import Unauthorized

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    return _password_hash.verify(password, password_hash)


def create_access_token(user_id: uuid.UUID, settings: Settings) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "iss": "contentpulse",
        "iat": datetime.now(UTC),
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_local_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer="contentpulse",
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Session expired. Please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise Unauthorized("Invalid authentication token.") from exc
    # Single-purpose tokens (password reset) are never sessions.
    if "purpose" in claims:
        raise Unauthorized("Invalid authentication token.")
    return claims


def generate_invite_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Only the hash is stored."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_invite_token(raw)


def hash_invite_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


_RESET_PURPOSE = "password_reset"


def _password_fingerprint(password_hash: str | None) -> str:
    # Ties a reset token to the current password, so it stops working once used.
    return hashlib.sha256((password_hash or "").encode()).hexdigest()[:16]


def create_password_reset_token(
    user_id: uuid.UUID, password_hash: str | None, settings: Settings
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iss": "contentpulse",
        "purpose": _RESET_PURPOSE,
        "pwf": _password_fingerprint(password_hash),
        "iat": now,
        "exp": now + timedelta(minutes=settings.password_reset_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def read_password_reset_token(token: str, settings: Settings) -> tuple[uuid.UUID, str]:
    """Return (user_id, password fingerprint) or raise Unauthorized."""
    invalid = "This reset link is invalid or has expired. Ask for a new one."
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer="contentpulse",
            options={"require": ["sub", "exp", "purpose", "pwf"]},
        )
        if claims["purpose"] != _RESET_PURPOSE:
            raise Unauthorized(invalid)
        return uuid.UUID(claims["sub"]), claims["pwf"]
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise Unauthorized(invalid) from exc


def password_matches_fingerprint(password_hash: str | None, fingerprint: str) -> bool:
    return secrets.compare_digest(_password_fingerprint(password_hash), fingerprint)
