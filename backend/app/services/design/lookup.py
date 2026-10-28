"""Finding a post's design brief. Kept apart from the design service so the
approval code can use it without importing the service that imports it."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.design import DesignBrief
from app.models.enums import DesignBriefStatus


async def latest_brief(db: AsyncSession, post_id: uuid.UUID, *conditions) -> DesignBrief | None:
    """The newest brief of the post that matches every extra condition."""
    return await db.scalar(
        select(DesignBrief)
        .where(DesignBrief.post_id == post_id, *conditions)
        .order_by(DesignBrief.created_at.desc())
        .limit(1)
    )


async def current_brief(db: AsyncSession, post_id: uuid.UUID) -> DesignBrief | None:
    """The post's live brief: the newest one that wasn't cancelled."""
    return await latest_brief(db, post_id, DesignBrief.status != DesignBriefStatus.CANCELLED)
