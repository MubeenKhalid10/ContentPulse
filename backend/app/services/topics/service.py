"""Topic candidates (spec §19, §20, §39)."""

import uuid

from sqlalchemy import case, func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidStateTransition, NotFound
from app.models.enums import RelevanceLevel, StrategyStatus, TopicStatus, TrendStatus
from app.models.topic import ContentStrategy, TopicCandidate
from app.models.trend import Trend
from app.schemas.topic import StrategyRead, TopicDetail, TopicListItem, TopicPage
from app.services import audit
from app.services.audit import AuditAction
from app.services.topics import sync
from app.services.trends.service import trend_detail

S = TopicStatus
STATUS_FILTERS: dict[str, list[TopicStatus] | None] = {
    "open": [S.NEW, S.REVIEWED],
    "new": [S.NEW],
    "reviewed": [S.REVIEWED],
    "shortlisted": [S.SHORTLISTED],
    "rejected": [S.REJECTED],
    "archived": [S.ARCHIVED],
    "all": None,
}
LEVEL_RANK = case(
    {
        RelevanceLevel.HIGHLY_RELEVANT: 0,
        RelevanceLevel.RELEVANT: 1,
        RelevanceLevel.WEAKLY_RELEVANT: 2,
        RelevanceLevel.NOT_RELEVANT: 3,
    },
    value=TopicCandidate.relevance_level,
    else_=4,
)


def _strategy_counts():
    live = ContentStrategy.status != StrategyStatus.ARCHIVED
    approved = ContentStrategy.status == StrategyStatus.APPROVED
    return (
        select(
            ContentStrategy.topic_id,
            func.count().filter(live).label("total"),
            func.count().filter(approved).label("approved"),
        )
        .group_by(ContentStrategy.topic_id)
        .subquery()
    )


async def list_topics(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    status: str,
    relevance: str | None,
    platform: str | None,
    q: str | None,
    sort: str,
    limit: int,
    offset: int,
) -> TopicPage:
    filters = [TopicCandidate.organization_id == organization_id]
    if relevance == "relevant":
        filters.append(
            TopicCandidate.relevance_level.in_(
                [RelevanceLevel.HIGHLY_RELEVANT, RelevanceLevel.RELEVANT]
            )
        )
    elif relevance:
        filters.append(TopicCandidate.relevance_level == RelevanceLevel(relevance))
    if platform:
        filters.append(TopicCandidate.recommended_platforms.contains([platform]))
    if q:
        filters.append(TopicCandidate.title.ilike(f"%{q.strip()}%"))

    counts = dict(
        (
            await db.execute(
                select(TopicCandidate.status, func.count())
                .where(*filters)
                .group_by(TopicCandidate.status)
            )
        ).all()
    )
    statuses = STATUS_FILTERS[status]
    if statuses is not None:
        filters.append(TopicCandidate.status.in_(statuses))

    strategies = _strategy_counts()
    order = {
        "score": [nulls_last(Trend.opportunity_score.desc()), TopicCandidate.created_at.desc()],
        "recent": [TopicCandidate.created_at.desc()],
        "relevance": [LEVEL_RANK, nulls_last(Trend.opportunity_score.desc())],
    }[sort]
    rows = await db.execute(
        select(
            TopicCandidate,
            Trend.opportunity_score,
            func.coalesce(strategies.c.total, 0),
            func.coalesce(strategies.c.approved, 0),
        )
        .outerjoin(Trend, Trend.id == TopicCandidate.trend_id)
        .outerjoin(strategies, strategies.c.topic_id == TopicCandidate.id)
        .where(*filters)
        .order_by(*order, TopicCandidate.id)
        .limit(limit)
        .offset(offset)
    )
    items = [
        TopicListItem.model_validate(topic).model_copy(
            update={
                "opportunity_score": score,
                "strategy_count": total,
                "approved_strategy_count": approved,
            }
        )
        for topic, score, total, approved in rows.all()
    ]
    total = await db.scalar(select(func.count()).select_from(TopicCandidate).where(*filters))
    return TopicPage(
        items=items,
        total=total or 0,
        counts={s.value: counts.get(s, 0) for s in TopicStatus},
    )


async def get_topic(
    db: AsyncSession, organization_id: uuid.UUID, topic_id: uuid.UUID
) -> TopicCandidate:
    topic = await db.scalar(
        select(TopicCandidate).where(
            TopicCandidate.id == topic_id, TopicCandidate.organization_id == organization_id
        )
    )
    if topic is None:
        raise NotFound("Topic")
    return topic


async def list_strategies(
    db: AsyncSession, organization_id: uuid.UUID, topic_id: uuid.UUID
) -> list[StrategyRead]:
    rows = await db.scalars(
        select(ContentStrategy)
        .where(
            ContentStrategy.organization_id == organization_id,
            ContentStrategy.topic_id == topic_id,
        )
        .order_by(ContentStrategy.created_at)
    )
    return [StrategyRead.model_validate(s) for s in rows]


async def topic_detail(
    db: AsyncSession, organization_id: uuid.UUID, topic_id: uuid.UUID
) -> TopicDetail:
    topic = await get_topic(db, organization_id, topic_id)
    trend = await db.get(Trend, topic.trend_id) if topic.trend_id else None
    strategies = await list_strategies(db, organization_id, topic.id)
    live = [s for s in strategies if s.status != StrategyStatus.ARCHIVED]
    fields = {
        name: getattr(topic, name) for name in TopicDetail.model_fields if hasattr(topic, name)
    }
    return TopicDetail.model_validate(
        {
            **fields,
            "opportunity_score": trend.opportunity_score if trend else None,
            "strategy_count": len(live),
            "approved_strategy_count": sum(s.status == StrategyStatus.APPROVED for s in live),
            "trend": await trend_detail(db, organization_id, trend.id) if trend else None,
            "strategies": strategies,
        }
    )


async def update_topic(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    topic_id: uuid.UUID,
    changes: dict,
) -> TopicDetail:
    topic = await get_topic(db, organization_id, topic_id)
    if topic.status == TopicStatus.ARCHIVED:
        raise InvalidStateTransition("Archived topics can't be edited.")
    old, new = audit.diff(topic, changes)
    for field, value in changes.items():
        setattr(topic, field, value)
    if new:
        audit.record(
            db,
            organization_id=organization_id,
            user_id=user_id,
            action=AuditAction.TOPIC_UPDATED,
            entity_type="topic",
            entity_id=topic.id,
            old_value=old,
            new_value=new,
        )
    await db.commit()
    return await topic_detail(db, organization_id, topic.id)


DELETABLE = (TopicStatus.SHORTLISTED, TopicStatus.REJECTED, TopicStatus.ARCHIVED)


async def delete_topic(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, topic_id: uuid.UUID
) -> None:
    """Permanently remove a shortlisted, rejected or archived topic with its plans
    (written posts are kept). Its trend goes too when that was also decided on,
    otherwise the startup backfill would bring the topic back."""
    topic = await get_topic(db, organization_id, topic_id)
    if topic.status not in DELETABLE:
        raise InvalidStateTransition(
            "Only shortlisted, rejected or archived topics can be deleted."
        )
    trend = await db.get(Trend, topic.trend_id) if topic.trend_id else None
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.TOPIC_DELETED,
        entity_type="topic",
        entity_id=topic.id,
        old_value={"status": topic.status, "title": topic.title},
    )
    await db.delete(topic)
    if trend is not None and trend.status in (
        TrendStatus.SHORTLISTED,
        TrendStatus.REJECTED,
        TrendStatus.ARCHIVED,
    ):
        await db.delete(trend)
    await db.commit()


async def transition(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    topic_id: uuid.UUID,
    target: TopicStatus,
) -> TopicDetail:
    topic = await get_topic(db, organization_id, topic_id)
    action = (
        AuditAction.TOPIC_RESTORED
        if target == TopicStatus.REVIEWED and topic.status == TopicStatus.REJECTED
        else None
    )
    sync.set_status(db, topic, target, user_id, action)
    await sync.on_topic_status(db, topic, target, user_id)
    await db.commit()
    return await topic_detail(db, organization_id, topic.id)
