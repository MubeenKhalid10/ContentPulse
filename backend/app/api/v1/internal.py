"""Machine-to-machine endpoints (not used by the web app).

POST /api/v1/internal/ingest/tick lets an external scheduler (Supabase Cron
via pg_net, see docs/supabase-cron.md) run one scheduler pass on the API, so
discovery happens on time even while the free Render instance would
otherwise be idle. It reuses the in-process scheduler's `tick()`: it starts
only the organizations that are due, and duplicate or concurrent deliveries
are harmless (advisory lock + one active run per organization).

Disabled (404) unless INGEST_TRIGGER_SECRET is set. The secret is compared in
constant time and never logged or echoed.
"""

import asyncio
import hmac

from fastapi import APIRouter, Request

from app.api.deps import AppSettings
from app.core.errors import AppError, ErrorCode, NotFound, Unauthorized
from app.core.logging import logger
from app.core.ratelimit import Rule, limiter
from app.workers import scheduler

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)

# A trigger needs no body; anything large is refused before it is read.
MAX_BODY_BYTES = 1024
# Generous for a 30-minute cron, tight enough to make hammering pointless.
TICK_RULE = Rule("ingest_tick", 6, 60, "Too many scheduler triggers.")
_running = asyncio.Lock()


def _presented_secret(request: Request) -> str:
    header = request.headers.get("x-ingest-secret")
    if header:
        return header.strip()
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


@router.post("/ingest/tick")
async def ingest_tick(request: Request, settings: AppSettings) -> dict:
    secret = settings.ingest_trigger_secret
    if not secret:
        raise NotFound("Route")
    if not hmac.compare_digest(_presented_secret(request).encode(), secret.encode()):
        raise Unauthorized("Invalid trigger secret.")
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Request body too large.", status_code=413)
    # One global bucket: client IPs aren't meaningful for a server-side caller.
    await limiter.check(TICK_RULE, "trigger")
    if _running.locked():
        # Another delivery is mid-pass in this process; the next tick catches up.
        return {"status": "busy", "scheduled": 0, "recovered": 0}
    async with _running:
        try:
            result = await scheduler.tick()
        except Exception:
            logger.exception("Triggered scheduler tick failed")
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                "Scheduler unavailable; try again later.",
                status_code=503,
            ) from None
    if result["scheduled"] or result["recovered"]:
        logger.info(
            "Triggered tick: %d run(s) started, %d stale run(s) closed",
            result["scheduled"],
            result["recovered"],
        )
    return {"status": "ok", **result}
