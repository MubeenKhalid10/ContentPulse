"""Build source inputs and the scoring profile from an organization's settings."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import OrganizationService, OrganizationSettings
from app.services.trends.scoring import OrgProfile
from app.sources.base import SourceInputs
from app.sources.locations import resolve_markets

MAX_KEYWORDS = 10


@dataclass
class OrgInputs:
    inputs: SourceInputs
    profile: OrgProfile
    unknown_markets: list[str]
    enabled_sources: list[str]


async def load_org_inputs(
    db: AsyncSession, organization_id: uuid.UUID, markets_override: list[str] | None = None
) -> OrgInputs:
    settings = await db.scalar(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == organization_id)
    )
    services = list(
        await db.scalars(
            select(OrganizationService.name).where(
                OrganizationService.organization_id == organization_id,
                OrganizationService.active.is_(True),
            )
        )
    )
    markets = markets_override or (settings.target_markets if settings else [])
    locations, unknown = resolve_markets(markets)
    tracked = settings.tracked_keywords if settings else []
    inputs = SourceInputs(
        locations=locations,
        # Tracked keywords drive keyword searches; services broaden them if few.
        keywords=list(dict.fromkeys([*tracked, *services]))[:MAX_KEYWORDS],
        subreddits=settings.subreddits if settings else [],
        rss_feeds=settings.rss_feeds if settings else [],
    )
    profile = OrgProfile(
        markets={loc.code for loc in locations},
        tracked_keywords=tracked,
        service_names=services,
    )
    return OrgInputs(
        inputs=inputs,
        profile=profile,
        unknown_markets=unknown,
        enabled_sources=settings.enabled_sources if settings else [],
    )
