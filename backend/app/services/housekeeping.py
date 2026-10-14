"""Daily clean-up: drop request history older than the retention window."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.core.config import get_settings
from app.core.logging import logger
from app.db.session import SessionLocal
from app.models.ai import LLMRequest


async def prune_llm_requests(now: datetime | None = None) -> int:
    days = get_settings().llm_request_retention_days
    if days <= 0:
        return 0
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    async with SessionLocal() as db:
        result = await db.execute(delete(LLMRequest).where(LLMRequest.created_at < cutoff))
        await db.commit()
    deleted = result.rowcount or 0
    if deleted:
        logger.info("Deleted %d model request record(s) older than %d days", deleted, days)
    return deleted


async def prune_provider_cache() -> int:
    """Delete shared provider responses past their stale window, and dead
    leases (bounded batches)."""
    from app.sources.provider_cache import store

    deleted = await store.prune(get_settings().provider_cache_stale_seconds)
    if deleted:
        logger.info("Deleted %d expired provider cache entr(ies)", deleted)
    return deleted


async def run_housekeeping(now: datetime | None = None) -> dict[str, int]:
    """Every clean-up task (hourly from the in-process scheduler and Celery beat)."""
    return {
        "llm_requests": await prune_llm_requests(now),
        "provider_cache": await prune_provider_cache(),
    }
