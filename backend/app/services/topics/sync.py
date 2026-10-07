"""Trend → topic candidate (spec §19-20).

A topic is created when alignment rates a trend relevant or highly relevant,
or when someone shortlists the trend. Re-analysis refreshes the topic's
analysis fields, never the human-edited title, summary or status. Shortlisting
or rejecting on either side is mirrored on the other.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.session import SessionLocal
from app.models.enums import RelevanceLevel, TopicStatus, TrendStatus
from app.models.organization import OrganizationSettings
from app.models.topic import TopicCandidate
from app.models.trend import Trend
from app.services import audit
from app.services.audit import AuditAction
from app.services.topics.platforms import RecommendationInput, get_rules, recommend
from app.services.workflow import TOPIC_MACHINE, TREND_MACHINE

TOPIC_LEVELS = (RelevanceLevel.HIGHLY_RELEVANT, RelevanceLevel.RELEVANT)
STATUS_ACTIONS = {
    TopicStatus.SHORTLISTED: AuditAction.TOPIC_SHORTLISTED,
    TopicStatus.REJECTED: AuditAction.TOPIC_REJECTED,
    TopicStatus.ARCHIVED: AuditAction.TOPIC_ARCHIVED,
}


async def _settings(db: AsyncSession, organization_id: uuid.UUID) -> OrganizationSettings | None:
    return await db.scalar(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == organization_id)
    )


async def analysis_fields(db: AsyncSession, trend: Trend) -> dict:
    """Topic fields derived from the trend and its alignment analysis."""
    settings = await _settings(db, trend.organization_id)
    rules = await get_rules(db, trend.organization_id)
    alignment = trend.alignment or {}
    angles = [
        {
            "title": a.get("title", ""),
            "angle": a.get("angle", ""),
            "platforms": a.get("platforms", []),
            "evidence": a.get("evidence", []),
        }
        for a in alignment.get("possible_angles", [])
    ]
    audience = " ".join(
        [settings.target_audience or "", *settings.content_goals] if settings else []
    )
    recommended, fit = recommend(
        RecommendationInput(
            enabled_platforms=settings.enabled_platforms if settings else [],
            audience_text=audience,
            topic_text=" ".join([trend.topic, *trend.keywords, trend.category or ""]),
            sources=trend.sources,
            angles=angles,
        ),
        rules,
    )
    return {
        "relevance_level": trend.relevance_level,
        "relevance_reason": alignment.get("reason"),
        "matched_services": alignment.get("matched_services", []),
        "suggested_angles": angles,
        "unsupported_claims": alignment.get("unsupported_claims", []),
        "recommended_platforms": recommended,
        "platform_fit": fit,
    }


# Organization settings that feed the platform recommendation.
FIT_SETTINGS = frozenset({"enabled_platforms", "target_audience", "content_goals"})


async def refresh_platform_fit(db: AsyncSession, organization_id: uuid.UUID) -> int:
    """Re-score the platforms of every open topic, e.g. after a platform such as
    Blog is enabled. Only the recommendation changes; returns how many topics."""
    topics = list(
        await db.scalars(
            select(TopicCandidate).where(
                TopicCandidate.organization_id == organization_id,
                TopicCandidate.status != TopicStatus.ARCHIVED,
                TopicCandidate.trend_id.is_not(None),
            )
        )
    )
    trend_ids = {t.trend_id for t in topics}
    trends = {
        t.id: t
        for t in (await db.scalars(select(Trend).where(Trend.id.in_(trend_ids))) if topics else [])
    }
    for topic in topics:
        if trend := trends.get(topic.trend_id):
            fields = await analysis_fields(db, trend)
            topic.recommended_platforms = fields["recommended_platforms"]
            topic.platform_fit = fields["platform_fit"]
    await db.commit()
    return len(topics)


async def topic_for_trend(db: AsyncSession, trend: Trend) -> TopicCandidate | None:
    return await db.scalar(
        select(TopicCandidate).where(
            TopicCandidate.organization_id == trend.organization_id,
            TopicCandidate.trend_id == trend.id,
        )
    )


async def sync_from_trend(
    db: AsyncSession, trend: Trend, *, create: bool = False
) -> TopicCandidate | None:
    """Create or refresh the trend's topic. `create` forces one (shortlisting)."""
    topic = await topic_for_trend(db, trend)
    if topic is None:
        wanted = create or trend.relevance_level in TOPIC_LEVELS
        if not wanted or trend.status in (TrendStatus.REJECTED, TrendStatus.ARCHIVED):
            return None
        settings = await _settings(db, trend.organization_id)
        topic = TopicCandidate(
            organization_id=trend.organization_id,
            trend_id=trend.id,
            title=trend.topic[:300],
            summary=trend.description or trend.title,
            target_audience=settings.target_audience if settings else None,
        )
        db.add(topic)
    if topic.status != TopicStatus.ARCHIVED:
        for field, value in (await analysis_fields(db, trend)).items():
            setattr(topic, field, value)
    await db.flush()
    return topic


def set_status(
    db: AsyncSession,
    topic: TopicCandidate,
    target: TopicStatus,
    user_id: uuid.UUID | None,
    action: AuditAction | None = None,
) -> None:
    TOPIC_MACHINE.assert_can(topic.status, target)
    previous = topic.status
    topic.status = target
    if user_id is not None:
        topic.reviewed_by = user_id
        topic.reviewed_at = datetime.now(UTC)
    audit.record(
        db,
        organization_id=topic.organization_id,
        user_id=user_id,
        action=action or STATUS_ACTIONS.get(target, AuditAction.TOPIC_REVIEWED),
        entity_type="topic",
        entity_id=topic.id,
        old_value={"status": previous},
        new_value={"status": target, "title": topic.title},
    )


async def on_trend_status(
    db: AsyncSession, trend: Trend, target: TrendStatus, user_id: uuid.UUID
) -> None:
    """Mirror a trend review decision onto its topic."""
    if target == TrendStatus.SHORTLISTED:
        topic = await sync_from_trend(db, trend, create=True)
        if topic and TOPIC_MACHINE.can(topic.status, TopicStatus.SHORTLISTED):
            set_status(db, topic, TopicStatus.SHORTLISTED, user_id)
        return
    topic = await topic_for_trend(db, trend)
    if topic is None:
        return
    if target == TrendStatus.REJECTED and TOPIC_MACHINE.can(topic.status, TopicStatus.REJECTED):
        set_status(db, topic, TopicStatus.REJECTED, user_id)
    elif target in (TrendStatus.NEW, TrendStatus.ANALYZED) and topic.status == TopicStatus.REJECTED:
        set_status(db, topic, TopicStatus.REVIEWED, user_id, AuditAction.TOPIC_RESTORED)


async def on_topic_status(
    db: AsyncSession, topic: TopicCandidate, target: TopicStatus, user_id: uuid.UUID
) -> None:
    """Mirror a topic decision onto its trend (kept in step for the Trends page)."""
    trend = await db.get(Trend, topic.trend_id) if topic.trend_id else None
    if trend is None:
        return
    goal: TrendStatus | None = None
    if target == TopicStatus.SHORTLISTED:
        goal = TrendStatus.SHORTLISTED
    elif target == TopicStatus.REJECTED:
        goal = TrendStatus.REJECTED
    elif target == TopicStatus.REVIEWED and trend.status in (
        TrendStatus.REJECTED,
        TrendStatus.SHORTLISTED,
    ):
        goal = TrendStatus.ANALYZED if trend.analyzed_at else TrendStatus.NEW
    if goal is None or trend.status == goal or not TREND_MACHINE.can(trend.status, goal):
        return
    previous = trend.status
    trend.status = goal
    audit.record(
        db,
        organization_id=trend.organization_id,
        user_id=user_id,
        action={
            TrendStatus.SHORTLISTED: AuditAction.TREND_SHORTLISTED,
            TrendStatus.REJECTED: AuditAction.TREND_REJECTED,
        }.get(goal, AuditAction.TREND_RESTORED),
        entity_type="trend",
        entity_id=trend.id,
        old_value={"status": previous},
        new_value={"status": goal, "topic": trend.topic},
    )


async def backfill() -> int:
    """Create topics for trends analyzed or shortlisted before topics existed.
    Idempotent; runs at startup."""
    created = 0
    async with SessionLocal() as db:
        trends = await db.scalars(
            select(Trend)
            .outerjoin(
                TopicCandidate,
                (TopicCandidate.trend_id == Trend.id)
                & (TopicCandidate.organization_id == Trend.organization_id),
            )
            .where(
                TopicCandidate.id.is_(None),
                (Trend.status == TrendStatus.SHORTLISTED)
                | (
                    Trend.relevance_level.in_(TOPIC_LEVELS)
                    & Trend.status.in_([TrendStatus.NEW, TrendStatus.ANALYZED])
                ),
            )
        )
        for trend in trends:
            topic = await sync_from_trend(db, trend, create=True)
            if topic and trend.status == TrendStatus.SHORTLISTED:
                topic.status = TopicStatus.SHORTLISTED
            created += topic is not None
        await db.commit()
    if created:
        logger.info("Created %d topic candidates from existing trends", created)
    return created
