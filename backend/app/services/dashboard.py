import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.enums import PostStatus, RelevanceLevel, TopicStatus, TrendStatus
from app.models.post import Post
from app.models.topic import TopicCandidate
from app.models.trend import Trend
from app.models.user import User
from app.schemas.dashboard import ActivityItem, DashboardSummary, TopTrend


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
