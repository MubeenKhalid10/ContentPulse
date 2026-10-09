import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalRequest
from app.models.audit import AuditLog
from app.models.enums import (
    ApprovalStatus,
    PostStatus,
    RelevanceLevel,
    TopicStatus,
    TrendStatus,
)
from app.models.organization import Organization
from app.models.post import Post
from app.models.topic import TopicCandidate
from app.models.trend import Trend
from app.models.user import User
from app.schemas.dashboard import (
    ActivityItem,
    DashboardOverview,
    DashboardSummary,
    Metric,
    PostBrief,
    TopTrend,
    TrendingTopic,
)


async def summary(db: AsyncSession, organization_id: uuid.UUID) -> DashboardSummary:
    """All dashboard counters in one round of queries (spec §43)."""
    since = datetime.now(UTC) - timedelta(hours=24)
    org = organization_id

    trend_counts = (
        await db.execute(
            select(
                func.count().filter(Trend.first_seen_at >= since),
                func.count().filter(
                    Trend.relevance_level.in_(
                        [RelevanceLevel.HIGHLY_RELEVANT, RelevanceLevel.RELEVANT]
                    ),
                    Trend.status.notin_([TrendStatus.REJECTED, TrendStatus.ARCHIVED]),
                ),
            ).where(Trend.organization_id == org)
        )
    ).one()

    shortlisted, to_review = (
        await db.execute(
            select(
                func.count().filter(TopicCandidate.status == TopicStatus.SHORTLISTED),
                func.count().filter(
                    TopicCandidate.status.in_([TopicStatus.NEW, TopicStatus.REVIEWED])
                ),
            ).where(TopicCandidate.organization_id == org)
        )
    ).one()

    post_counts: dict[PostStatus, int] = dict(
        (
            await db.execute(
                select(Post.status, func.count())
                .where(Post.organization_id == org)
                .group_by(Post.status)
            )
        ).all()
    )

    top = await db.scalars(
        select(Trend)
        .where(
            Trend.organization_id == org,
            Trend.status.in_([TrendStatus.NEW, TrendStatus.ANALYZED]),
            Trend.last_seen_at >= datetime.now(UTC) - timedelta(days=7),
            Trend.opportunity_score.is_not(None),
            or_(
                Trend.relevance_level.is_(None),
                Trend.relevance_level != RelevanceLevel.NOT_RELEVANT,
            ),
        )
        .order_by(Trend.opportunity_score.desc())
        .limit(5)
    )

    activity_rows = await db.execute(
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(AuditLog.organization_id == org)
        .order_by(AuditLog.created_at.desc())
        .limit(10)
    )

    return DashboardSummary(
        trends_today=trend_counts[0],
        relevant_trends=trend_counts[1],
        shortlisted_topics=shortlisted or 0,
        topics_to_review=to_review or 0,
        drafts=post_counts.get(PostStatus.DRAFT, 0) + post_counts.get(PostStatus.CONTENT_REVIEW, 0),
        # Design queue: everything a designer still has to act on.
        design_pending=sum(
            post_counts.get(s, 0)
            for s in (
                PostStatus.DESIGN_PENDING,
                PostStatus.DESIGN_IN_PROGRESS,
                PostStatus.DESIGN_UPLOADED,
                PostStatus.CHANGES_REQUESTED,
            )
        ),
        pending_approval=post_counts.get(PostStatus.PENDING_APPROVAL, 0),
        approved=post_counts.get(PostStatus.APPROVED, 0) + post_counts.get(PostStatus.FINAL, 0),
        top_trends=[
            TopTrend(
                id=t.id,
                topic=t.topic,
                opportunity_score=t.opportunity_score,
                sources=t.sources,
                mention_count=t.mention_count,
            )
            for t in top
        ],
        recent_activity=[
            ActivityItem(
                id=log.id,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                user_name=name,
                created_at=log.created_at,
            )
            for log, name in activity_rows
        ],
    )


# --- Overview (the dashboard page) --------------------------------------------------

PERIODS = (7, 30, 90)
PIPELINE = {
    "draft": (PostStatus.DRAFT, PostStatus.CONTENT_REVIEW),
    "design": (
        PostStatus.DESIGN_PENDING,
        PostStatus.DESIGN_IN_PROGRESS,
        PostStatus.DESIGN_UPLOADED,
    ),
    "approval": (PostStatus.PENDING_APPROVAL,),
    "changes": (PostStatus.CHANGES_REQUESTED,),
    "ready": (PostStatus.APPROVED, PostStatus.FINAL),
}
RELEVANT = (RelevanceLevel.HIGHLY_RELEVANT, RelevanceLevel.RELEVANT)


async def _metric(
    db: AsyncSession,
    column,
    conditions: list,
    *,
    start: datetime,
    end: datetime,
    days: int,
    timezone: str,
) -> Metric:
    """Count in [start, end), in the same number of days before it, and per local day."""
    previous_start = start - timedelta(days=days)
    counts = (
        await db.execute(
            select(
                func.count().filter(column >= start, column < end),
                func.count().filter(column >= previous_start, column < start),
            ).where(*conditions)
        )
    ).one()
    local_day = func.date_trunc("day", func.timezone(timezone, column))
    rows = await db.execute(
        select(local_day, func.count())
        .where(*conditions, column >= start, column < end)
        .group_by(local_day)
    )
    per_day = {day.date(): n for day, n in rows if day is not None}
    first = start.astimezone(ZoneInfo(timezone)).date()
    series = [per_day.get(first + timedelta(days=i), 0) for i in range(days)]
    return Metric(value=counts[0], previous=counts[1], series=series)


async def overview(
    db: AsyncSession, organization_id: uuid.UUID, days: int = 7
) -> DashboardOverview:
    """Everything the dashboard page shows, for the last `days` days."""
    days = days if days in PERIODS else 7
    org = organization_id
    organization = await db.get(Organization, org)
    timezone = organization.timezone if organization else "UTC"
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        timezone = "UTC"
    # Whole local days: today and the days before it, from midnight.
    zone = ZoneInfo(timezone)
    end = datetime.now(UTC)
    today = end.astimezone(zone).date()
    start = datetime.combine(today - timedelta(days=days - 1), time.min, zone).astimezone(UTC)
    window = {"start": start, "end": end, "days": days, "timezone": timezone}

    trends_discovered = await _metric(
        db, Trend.first_seen_at, [Trend.organization_id == org], **window
    )
    relevant_trends = await _metric(
        db,
        Trend.first_seen_at,
        [Trend.organization_id == org, Trend.relevance_level.in_(RELEVANT)],
        **window,
    )
    posts_generated = await _metric(db, Post.created_at, [Post.organization_id == org], **window)
    approved_posts = await _metric(
        db,
        ApprovalRequest.reviewed_at,
        [
            ApprovalRequest.organization_id == org,
            ApprovalRequest.status == ApprovalStatus.APPROVED,
        ],
        **window,
    )

    by_status: dict[PostStatus, int] = dict(
        (
            await db.execute(
                select(Post.status, func.count())
                .where(Post.organization_id == org)
                .group_by(Post.status)
            )
        ).all()
    )
    pipeline = {
        stage: sum(by_status.get(s, 0) for s in statuses) for stage, statuses in PIPELINE.items()
    }

    platform_rows = await db.execute(
        select(Post.platform, func.count())
        .where(
            Post.organization_id == org,
            Post.status.notin_([PostStatus.ARCHIVED, PostStatus.REJECTED]),
        )
        .group_by(Post.platform)
    )
    platforms = {str(platform): n for platform, n in platform_rows}

    trends = await db.scalars(
        select(Trend)
        .where(
            Trend.organization_id == org,
            Trend.last_seen_at >= start,
            Trend.status.notin_([TrendStatus.REJECTED, TrendStatus.ARCHIVED]),
        )
        .order_by(Trend.opportunity_score.desc().nulls_last(), Trend.last_seen_at.desc())
        .limit(20)
    )
    trending = []
    for t in trends:
        growth = (t.signals or {}).get("growth")
        score = growth.get("score") if isinstance(growth, dict) else None
        reason = (t.alignment or {}).get("reason")
        trending.append(
            TrendingTopic(
                id=t.id,
                topic=t.topic,
                source=t.sources[0] if t.sources else None,
                category=t.category,
                relevance_level=t.relevance_level.value if t.relevance_level else None,
                opportunity_score=t.opportunity_score,
                momentum=round(score) if isinstance(score, int | float) else None,
                why=reason[:220] if isinstance(reason, str) and reason else None,
                shortlisted=t.status == TrendStatus.SHORTLISTED,
            )
        )

    recent = await db.scalars(
        select(Post).where(Post.organization_id == org).order_by(Post.updated_at.desc()).limit(6)
    )

    return DashboardOverview(
        days=days,
        start=start,
        end=end,
        trends_discovered=trends_discovered,
        relevant_trends=relevant_trends,
        posts_generated=posts_generated,
        approved_posts=approved_posts,
        pending_approval=by_status.get(PostStatus.PENDING_APPROVAL, 0),
        trending=trending,
        platform_breakdown=platforms,
        pipeline=pipeline,
        recent_posts=[
            PostBrief(
                id=p.id,
                title=p.title,
                platform=str(p.platform),
                status=str(p.status),
                updated_at=p.updated_at,
            )
            for p in recent
        ],
    )
