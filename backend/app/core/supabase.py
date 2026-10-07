"""Supabase access-token verification.

Supabase projects sign tokens either with asymmetric keys (ES256/RS256,
published at /auth/v1/.well-known/jwks.json, the current default) or with
the legacy shared JWT secret (HS256). Both are supported; keys are cached and
refreshed when a token names a key we haven't seen (key rotation).
"""

import asyncio
import time
from typing import Any

import httpx
import jwt

from app.core.config import Settings
from app.core.errors import Unauthorized
from app.core.logging import logger

JWKS_TTL_SECONDS = 600
ASYMMETRIC = {"ES256", "RS256", "EdDSA"}


class JWKSCache:
    def __init__(self) -> None:
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    def clear(self) -> None:
        self._keys.clear()
        self._fetched_at = 0.0

    async def _refresh(self, url: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            keys = resp.json().get("keys", [])
        self._keys = {k["kid"]: jwt.PyJWK(k) for k in keys if k.get("kid")}
        self._fetched_at = time.monotonic()

    async def get(self, kid: str, settings: Settings) -> jwt.PyJWK:
        url = f"{(settings.supabase_url or '').rstrip('/')}/auth/v1/.well-known/jwks.json"
        expired = time.monotonic() - self._fetched_at > JWKS_TTL_SECONDS
        if kid not in self._keys or expired:
            async with self._lock:
                if kid not in self._keys or time.monotonic() - self._fetched_at > JWKS_TTL_SECONDS:
                    try:
                        await self._refresh(url)
                    except (httpx.HTTPError, ValueError, jwt.PyJWKError) as exc:
                        logger.warning("Could not load Supabase signing keys: %s", exc)
                        if kid not in self._keys:
                            raise Unauthorized(
                                "Could not verify the sign-in. Try again shortly."
                            ) from exc
        if kid not in self._keys:
            raise Unauthorized("Invalid authentication token.")
        return self._keys[kid]


jwks_cache = JWKSCache()


async def verify_supabase_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise Unauthorized("Invalid authentication token.") from exc
    alg = header.get("alg")
    if alg in ASYMMETRIC:
        if not settings.supabase_url:
            raise Unauthorized("Supabase sign-in is not configured.")
        key: Any = (await jwks_cache.get(header.get("kid") or "", settings)).key
    elif alg == "HS256" and settings.supabase_jwt_secret:
        key = settings.supabase_jwt_secret
    else:
        raise Unauthorized("Invalid authentication token.")

    options: dict[str, Any] = {"require": ["sub", "exp"]}
    issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1" if settings.supabase_url else None
    try:
        return jwt.decode(
            token,
            key,
            algorithms=[alg],
            audience="authenticated",
            issuer=issuer,
            options=options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Session expired. Please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise Unauthorized("Invalid authentication token.") from exc
