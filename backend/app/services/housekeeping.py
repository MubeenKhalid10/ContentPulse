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
