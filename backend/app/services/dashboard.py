import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import Role
from app.models.audit import AuditLog
from app.models.enums import (
    PostStatus,
    RelevanceLevel,
    TopicStatus,
    TrendStatus,
)
from app.models.organization import Organization
from app.models.post import Post, PostVersion
from app.models.topic import TopicCandidate
from app.models.trend import Trend
from app.models.user import User
from app.schemas.dashboard import (
    ActivityItem,
    Attention,
    DashboardOverview,
    DashboardSummary,
    Metric,
    PostBrief,
    TopTrend,
    TrendingTopic,
)
from app.services.audit import AuditAction
from app.services.trends import visibility


async def attention(db: AsyncSession, organization_id: uuid.UUID) -> Attention:
    """The counts behind the sidebar badges, without the rest of the summary."""
    to_review = await db.scalar(
        select(func.count()).where(
            TopicCandidate.organization_id == organization_id,
            TopicCandidate.status.in_([TopicStatus.NEW, TopicStatus.REVIEWED]),
        )
    )
    post_counts: dict[PostStatus, int] = dict(
        (
            await db.execute(
                select(Post.status, func.count())
                .where(Post.organization_id == organization_id)
                .group_by(Post.status)
            )
        ).all()
    )
    return Attention(
        to_review=to_review or 0,
        design=sum(
            post_counts.get(s, 0)
            for s in (
                PostStatus.DESIGN_PENDING,
                PostStatus.DESIGN_IN_PROGRESS,
                PostStatus.DESIGN_UPLOADED,
                PostStatus.CHANGES_REQUESTED,
            )
        ),
        approvals=post_counts.get(PostStatus.PENDING_APPROVAL, 0)
        + post_counts.get(PostStatus.CONTENT_REVIEW, 0),
    )


async def summary(db: AsyncSession, organization_id: uuid.UUID) -> DashboardSummary:
    """All dashboard counters in one round of queries (spec §43)."""
    since = datetime.now(UTC) - timedelta(hours=24)
    org = organization_id
    shown = visibility.visible(await visibility.feed_sources(db, org))

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
            ).where(Trend.organization_id == org, shown)
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
            shown,
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
        drafts=post_counts.get(PostStatus.DRAFT, 0),
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
        # Copy awaiting approval plus designs awaiting approval.
        pending_approval=post_counts.get(PostStatus.PENDING_APPROVAL, 0)
        + post_counts.get(PostStatus.CONTENT_REVIEW, 0),
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
APPROVAL_STAGE_STATUSES = (
    PostStatus.CONTENT_REVIEW,
    PostStatus.PENDING_APPROVAL,
    PostStatus.CHANGES_REQUESTED,
)
PIPELINE = {
    "draft": (PostStatus.DRAFT,),
    "design": (
        PostStatus.DESIGN_PENDING,
        PostStatus.DESIGN_IN_PROGRESS,
        PostStatus.DESIGN_UPLOADED,
    ),
    "approval": (PostStatus.CONTENT_REVIEW, PostStatus.PENDING_APPROVAL),
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
    db: AsyncSession,
    organization_id: uuid.UUID,
    days: int = 7,
    *,
    role: Role = Role.ADMIN,
    user_id: uuid.UUID | None = None,
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
    enabled = await visibility.feed_sources(db, org)
    shown = visibility.visible(enabled)

    trends_discovered = await _metric(
        db, Trend.first_seen_at, [Trend.organization_id == org, shown], **window
    )
    relevant_trends = await _metric(
        db,
        Trend.first_seen_at,
        [Trend.organization_id == org, shown, Trend.relevance_level.in_(RELEVANT)],
        **window,
    )
    posts_generated = await _metric(db, Post.created_at, [Post.organization_id == org], **window)
    # Final (design-stage) approvals, counted from the audit trail: the copy
    # review isn't a finished post, and reopening approved work rewrites the
    # request row but never the fact that it was approved.
    approved_posts = await _metric(
        db,
        AuditLog.created_at,
        [
            AuditLog.organization_id == org,
            AuditLog.action == AuditAction.APPROVED,
            AuditLog.entity_type == "post",
            AuditLog.new_value["stage"].astext.is_(None),
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
            shown,
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
                source=next((s for s in t.sources if s in enabled), None),
                category=t.category,
                relevance_level=t.relevance_level.value if t.relevance_level else None,
                opportunity_score=t.opportunity_score,
                momentum=round(score) if isinstance(score, int | float) else None,
                why=reason[:220] if isinstance(reason, str) and reason else None,
                shortlisted=t.status == TrendStatus.SHORTLISTED,
            )
        )

    # Admins see everything (with who wrote it); creators their own posts; viewers
    # nothing that is in an approval stage.
    recent_query = select(Post).where(Post.organization_id == org)
    if role == Role.CREATOR:
        recent_query = recent_query.where(Post.created_by == user_id)
    elif role == Role.VIEWER:
        recent_query = recent_query.where(Post.status.notin_(APPROVAL_STAGE_STATUSES))
    recent = await db.scalars(recent_query.order_by(Post.updated_at.desc()).limit(8))

    recent_list = list(recent)
    copy_by_post: dict[uuid.UUID, str] = {}
    creator_by_post: dict[uuid.UUID, str] = {}
    if role == Role.ADMIN and recent_list:
        people = await db.execute(
            select(User.id, User.full_name, User.email).where(
                User.id.in_({p.created_by for p in recent_list if p.created_by})
            )
        )
        names = {r[0]: (r[1] or r[2]) for r in people}
        creator_by_post = {p.id: names[p.created_by] for p in recent_list if p.created_by in names}
    if recent_list:
        rows = await db.execute(
            select(
                PostVersion.post_id, PostVersion.version_number, PostVersion.hook, PostVersion.body
            ).where(PostVersion.post_id.in_([p.id for p in recent_list]))
        )
        versions = {(r[0], r[1]): " ".join(f"{r[2] or ''} {r[3] or ''}".split()) for r in rows}
        for p in recent_list:
            text = versions.get((p.id, p.current_version))
            if text:
                copy_by_post[p.id] = text[:240]

    return DashboardOverview(
        days=days,
        start=start,
        end=end,
        trends_discovered=trends_discovered,
        relevant_trends=relevant_trends,
        posts_generated=posts_generated,
        approved_posts=approved_posts,
        pending_approval=by_status.get(PostStatus.PENDING_APPROVAL, 0)
        + by_status.get(PostStatus.CONTENT_REVIEW, 0),
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
                excerpt=copy_by_post.get(p.id),
                version=p.current_version,
                creator_name=creator_by_post.get(p.id),
            )
            for p in recent_list
        ],
    )
