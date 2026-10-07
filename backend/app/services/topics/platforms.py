"""Platform playbooks (spec §22) and explainable platform recommendation."""

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Platform
from app.models.topic import PlatformRule
from app.services import audit
from app.services.audit import AuditAction
from app.services.topics.platform_defaults import DEFAULT_RULES
from app.sources import SOURCES

PLATFORM_LABELS = {
    Platform.LINKEDIN: "LinkedIn",
    Platform.X: "X",
    Platform.INSTAGRAM: "Instagram",
    Platform.FACEBOOK: "Facebook",
    Platform.BLOG: "Blog",
}
EDITABLE = (
    "post_types",
    "objectives",
    "affinity_keywords",
    "tone",
    "guidance",
    "max_length",
    "hashtag_limit",
)


async def get_rules(db: AsyncSession, organization_id: uuid.UUID) -> dict[Platform, PlatformRule]:
    """The organization's playbook for every platform, seeding defaults once."""
    rules = {
        r.platform: r
        for r in await db.scalars(
            select(PlatformRule).where(PlatformRule.organization_id == organization_id)
        )
    }
    missing = [p for p in Platform if p not in rules]
    if missing:
        await db.execute(
            insert(PlatformRule)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "organization_id": organization_id,
                        "platform": p,
                        **DEFAULT_RULES[p],
                    }
                    for p in missing
                ]
            )
            .on_conflict_do_nothing(constraint="uq_platform_rules_organization_id")
        )
        await db.flush()
        return await get_rules(db, organization_id)
    return dict(sorted(rules.items(), key=lambda kv: list(Platform).index(kv[0])))


async def update_rule(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    platform: Platform,
    changes: dict[str, Any],
) -> PlatformRule:
    rule = (await get_rules(db, organization_id))[platform]
    old, new = audit.diff(rule, changes)
    for field, value in changes.items():
        setattr(rule, field, value)
    if new:
        audit.record(
            db,
            organization_id=organization_id,
            user_id=user_id,
            action=AuditAction.PLATFORM_RULES_UPDATED,
            entity_type="platform_rule",
            entity_id=rule.id,
            old_value={"platform": platform, **old},
            new_value={"platform": platform, **new},
        )
    await db.commit()
    await db.refresh(rule)
    return rule


async def reset_rule(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, platform: Platform
) -> PlatformRule:
    return await update_rule(db, organization_id, user_id, platform, dict(DEFAULT_RULES[platform]))


# --- Recommendation ------------------------------------------------------------------

# Where a trend is already being discussed hints at where it travels well.
SOURCE_AFFINITY: dict[str, dict[Platform, int]] = {
    "x": {Platform.X: 12},
    "instagram": {Platform.INSTAGRAM: 12},
    "linkedin": {Platform.LINKEDIN: 12},
    "hacker_news": {Platform.X: 8, Platform.LINKEDIN: 4, Platform.BLOG: 4},
    "reddit": {Platform.X: 6, Platform.FACEBOOK: 4},
    "google_news": {Platform.LINKEDIN: 6, Platform.FACEBOOK: 4, Platform.BLOG: 3},
    "newsapi": {Platform.LINKEDIN: 6, Platform.FACEBOOK: 4, Platform.BLOG: 3},
    "gnews": {Platform.LINKEDIN: 6, Platform.FACEBOOK: 4, Platform.BLOG: 3},
    "rss": {Platform.LINKEDIN: 4, Platform.BLOG: 4},
    # Search interest is what long-form articles rank for.
    "google_trends": {
        Platform.INSTAGRAM: 3,
        Platform.FACEBOOK: 3,
        Platform.X: 3,
        Platform.BLOG: 6,
    },
}
BASE_SCORE = 30
RECOMMEND_AT = 50


@dataclass
class RecommendationInput:
    enabled_platforms: list[str]
    audience_text: str  # target audience + content goals
    topic_text: str  # topic, keywords, category
    sources: list[str]
    angles: list[dict]  # alignment possible_angles: {title, platforms, ...}


def _matches(keywords: list[str], text: str) -> list[str]:
    text = text.lower()
    return [k for k in keywords if re.search(rf"(?<!\w){re.escape(k.lower())}(?!\w)", text)]


def recommend(
    data: RecommendationInput, rules: dict[Platform, PlatformRule]
) -> tuple[list[str], list[dict]]:
    """Score each enabled platform 0-100 with the reasons behind the score.

    Returns (recommended platforms, fit details sorted best first).
    """
    enabled = [Platform(p) for p in data.enabled_platforms if p in Platform] or list(Platform)
    fits: list[dict] = []
    for platform in enabled:
        rule = rules[platform]
        label = PLATFORM_LABELS[platform]
        score, reasons = BASE_SCORE, []

        angles = [a for a in data.angles if platform.value in (a.get("platforms") or [])]
        if angles:
            score += min(30, 20 + 5 * (len(angles) - 1))
            reasons.append(f'Suggested angle for {label}: "{angles[0].get("title", "")}"')

        audience_hits = _matches(rule.affinity_keywords, data.audience_text)
        if audience_hits:
            score += min(24, 8 * len(audience_hits))
            reasons.append(f"Fits your audience and goals: {', '.join(audience_hits[:3])}")
        topic_hits = [
            k for k in _matches(rule.affinity_keywords, data.topic_text) if k not in audience_hits
        ]
        if topic_hits:
            score += min(10, 5 * len(topic_hits))
            reasons.append(f"The topic plays well here: {', '.join(topic_hits[:3])}")

        boost, boosted_by = 0, []
        for key in data.sources:
            if points := SOURCE_AFFINITY.get(key, {}).get(platform):
                boost += points
                source = SOURCES.get(key)
                boosted_by.append(source.name if source else key)
        if boost:
            score += min(15, boost)
            reasons.append(f"Already being discussed on {', '.join(boosted_by[:3])}")

        if not reasons:
            reasons.append(f"{label} is one of your active platforms")
        fits.append(
            {
                "platform": platform.value,
                "score": max(0, min(100, score)),
                "reasons": reasons,
                "formats": rule.post_types[:3],
            }
        )

    fits.sort(key=lambda f: -f["score"])  # stable: keeps the configured order on ties
    recommended = [f["platform"] for f in fits if f["score"] >= RECOMMEND_AT]
    if not recommended and fits:
        recommended = [fits[0]["platform"]]
    return recommended, fits
