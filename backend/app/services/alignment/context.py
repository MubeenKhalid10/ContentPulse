"""Organization context for alignment (spec §15 input)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Platform
from app.models.organization import (
    BrandProfile,
    Organization,
    OrganizationService,
    OrganizationSettings,
)
from app.services.trends.scoring import OrgProfile
from app.sources.locations import resolve_markets

ALL_PLATFORMS = [p.value for p in Platform]


@dataclass
class AlignmentContext:
    organization_id: uuid.UUID
    name: str
    profile_text: str
    service_names: list[str]
    platforms: list[str]
    scoring_profile: OrgProfile


def _line(label: str, value: str | None) -> str | None:
    return f"{label}: {value.strip()}" if value and value.strip() else None


async def load_context(db: AsyncSession, organization_id: uuid.UUID) -> AlignmentContext:
    org = await db.get(Organization, organization_id)
    assert org is not None
    settings = await db.scalar(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == organization_id)
    )
    brand = await db.scalar(
        select(BrandProfile).where(BrandProfile.organization_id == organization_id)
    )
    services = list(
        await db.scalars(
            select(OrganizationService)
            .where(
                OrganizationService.organization_id == organization_id,
                OrganizationService.active.is_(True),
            )
            .order_by(OrganizationService.kind, OrganizationService.name)
        )
    )
    markets = settings.target_markets if settings else []
    platforms = (settings.enabled_platforms if settings else []) or ALL_PLATFORMS

    lines = [
        _line("Name", org.name),
        _line("Website", org.website_url),
        _line("Industry", org.industry),
        _line("What the organization does", org.description),
        _line("Target audience", settings.target_audience if settings else None),
        _line("Target markets", ", ".join(markets) or "Global"),
        _line("Content goals", ", ".join(settings.content_goals) if settings else None),
        _line("Topics it tracks", ", ".join(settings.tracked_keywords) if settings else None),
        _line("Publishes on", ", ".join(platforms)),
    ]
    if services:
        lines.append(
            "Services, products and expertise (the only offerings you may attribute to it):"
        )
        for s in services:
            detail = f" ({s.category})" if s.category else ""
            desc = f": {s.description.strip()}" if s.description else ""
            lines.append(f"- [{s.kind}] {s.name}{detail}{desc}")
    else:
        lines.append("Services, products and expertise: none listed yet.")
    if brand:
        lines += [
            _line("Brand voice", brand.brand_voice),
            _line("Tone", brand.tone),
            _line("Never use these terms", ", ".join(brand.forbidden_terms)),
            _line("Content guidelines", brand.content_guidelines),
            _line("Calls to action", brand.cta_guidelines),
        ]

    locations, _ = resolve_markets(markets)
    return AlignmentContext(
        organization_id=organization_id,
        name=org.name,
        profile_text="\n".join(line for line in lines if line),
        service_names=[s.name for s in services],
        platforms=platforms,
        scoring_profile=OrgProfile(
            markets={loc.code for loc in locations},
            tracked_keywords=settings.tracked_keywords if settings else [],
            service_names=[s.name for s in services],
        ),
    )
