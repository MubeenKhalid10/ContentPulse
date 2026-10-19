"""Discovery Sources: which sources' trends appear in an organization's feed.

The preference is `organization_settings.enabled_sources`, the same per-org
list that already selects which providers this organization's discovery runs
ask (through the shared provider cache and quota controls). Attribution comes
from `trend_mentions.source`: a trend is visible when at least one of its
mentions came from a source that is both enabled and in the registry.

A trend with no mentions, or only mentions from source keys the registry no
longer knows, has no usable attribution and is hidden rather than exposed.
Filtering is a pure database query: it never calls a provider.
"""

import uuid

from sqlalchemy import ColumnElement, exists, false, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import OrganizationSettings
from app.models.trend import Trend, TrendMention
from app.sources import SOURCES


async def feed_sources(db: AsyncSession, organization_id: uuid.UUID) -> list[str]:
    """The registered sources this organization has switched on."""
    enabled = await db.scalar(
        select(OrganizationSettings.enabled_sources).where(
            OrganizationSettings.organization_id == organization_id
        )
    )
    return [key for key in enabled or [] if key in SOURCES]


def visible(sources: list[str]) -> ColumnElement[bool]:
    """WHERE condition on `Trend`: reported by at least one of `sources`."""
    if not sources:
        return false()
    return exists().where(
        TrendMention.trend_id == Trend.id,
        TrendMention.organization_id == Trend.organization_id,
        TrendMention.source.in_(sources),
    )
