"""Cloudflare Turnstile check for local sign-in (sign-up, sign-in, password reset).

Off unless TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY are both set. In Supabase
mode Supabase runs its own CAPTCHA, so nothing here applies. The check fails
closed: if Cloudflare can't be reached, the request is refused (503), never waved
through.
"""

from typing import Any

import httpx
from fastapi import Request

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, ServiceUnavailable
from app.core.logging import logger
from app.core.ratelimit import limiter

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def _siteverify(token: str, remote_ip: str, settings: Settings) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        response = await client.post(
            SITEVERIFY_URL,
            data={
                "secret": settings.turnstile_secret_key or "",
                "response": token,
                "remoteip": remote_ip,
            },
        )
        response.raise_for_status()
        body = response.json()
    return body if isinstance(body, dict) else {}


async def require_captcha(request: Request, token: str | None, settings: Settings) -> None:
    """Raise unless `token` is a solved Turnstile challenge (when CAPTCHA is on)."""
    if not settings.captcha_enabled:
        return
    if not token:
        raise AppError(
            ErrorCode.VALIDATION_ERROR, "Complete the CAPTCHA challenge.", status_code=400
        )
    try:
        result = await _siteverify(token, limiter.client_ip(request), settings)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Turnstile verification unavailable: %s", exc.__class__.__name__)
        raise ServiceUnavailable("Could not verify the CAPTCHA. Try again shortly.") from exc
    if result.get("success") is not True:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "The CAPTCHA check failed. Try again.",
            status_code=400,
        )
