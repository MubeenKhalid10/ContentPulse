"""Trend operations used by the API (spec §38)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Text, cast, func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, InvalidStateTransition, NotFound
from app.models.ai import AIGenerationJob
from app.models.enums import (
    DiscoveryRunStatus,
    RelevanceLevel,
    RunTrigger,
    SourceHealth,
    TrendStatus,
)
from app.models.organization import OrganizationSettings
from app.models.trend import Trend, TrendDiscoveryRun, TrendMention, TrendSource
from app.schemas.trend import (
    AnalysisStatus,
    MentionRead,
    SourceInfo,
    TrendDetail,
    TrendListItem,
    TrendPage,
)
from app.services import audit
from app.services.alignment import service as alignment
from app.services.audit import AuditAction
from app.services.topics import sync as topic_sync
from app.services.trends.inputs import load_org_inputs
from app.services.workflow import TREND_MACHINE
from app.sources import SOURCES
from app.workers import trend_tasks
from app.workers.tasks import enqueue

ACTIVE_RUN = (DiscoveryRunStatus.QUEUED, DiscoveryRunStatus.RUNNING)


async def list_sources(
    db: AsyncSession, organization_id: uuid.UUID, settings: Settings
) -> list[SourceInfo]:
    org = await load_org_inputs(db, organization_id)
    health = {row.key: row for row in await db.scalars(select(TrendSource))}
    out = []
    for source in SOURCES.values():
        config = source.configuration(settings, org.inputs)
        row = health.get(source.key)
        out.append(
            SourceInfo(
                key=source.key,
                name=source.name,
                description=source.description,
                pricing=source.pricing,
                docs_url=source.docs_url,
                env_vars=list(source.env_vars),
                configured=config.configured,
                mode=config.mode,
                missing=list(config.missing),
                note=config.note,
                enabled=source.key in org.enabled_sources,
                health=row.health if row else SourceHealth.UNKNOWN,
                last_success_at=row.last_success_at if row else None,
                last_failure_at=row.last_failure_at if row else None,
                last_error=row.last_error if row else None,
            )
        )
    return out


async def set_source_enabled(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, key: str, enabled: bool
) -> None:
    if key not in SOURCES:
        raise NotFound("Source")
    settings_row = await db.scalar(
        select(OrganizationSettings)
        .where(OrganizationSettings.organization_id == organization_id)
        .with_for_update()
    )
    if settings_row is None:
        raise NotFound("Organization settings")
    current = list(settings_row.enabled_sources)
    if enabled:
        updated = current if key in current else [*current, key]
    else:
        updated = [k for k in current if k != key]
    if updated == current:
        return
    settings_row.enabled_sources = updated
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.SETTINGS_UPDATED,
        entity_type="organization_settings",
        entity_id=settings_row.id,
        old_value={"enabled_sources": current},
        new_value={"enabled_sources": updated},
    )
    await db.commit()


async def start_discovery(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID | None,
    sources: list[str] | None,
    locations: list[str] | None,
) -> TrendDiscoveryRun:
    unknown = [s for s in sources or [] if s not in SOURCES]
    if unknown:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"Unknown source(s): {', '.join(unknown)}.",
            details={"available": sorted(SOURCES)},
        )
    org = await load_org_inputs(db, organization_id)
    chosen = sources if sources is not None else org.enabled_sources
    if not chosen:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "No trend sources are enabled. Enable at least one in Trends › Sources.",
        )

    active = await db.scalar(
        select(TrendDiscoveryRun)
        .where(
            TrendDiscoveryRun.organization_id == organization_id,
            TrendDiscoveryRun.status.in_(ACTIVE_RUN),
        )
        .with_for_update()
    )
    if active is not None:
        stale = await db.scalar(
            select(func.count())
            .select_from(TrendDiscoveryRun)
            .where(TrendDiscoveryRun.id == active.id, trend_tasks.stale_condition())
        )
        if not stale:
            raise AppError(
                ErrorCode.CONFLICT,
                "Trend discovery is already running.",
                details={"run_id": str(active.id)},
            )
        active.status = DiscoveryRunStatus.FAILED
        active.error = "Interrupted: the worker stopped responding."
        active.finished_at = datetime.now(UTC)

    run = TrendDiscoveryRun(
        organization_id=organization_id,
        trigger=RunTrigger.MANUAL,
        sources=list(dict.fromkeys(chosen)),
        locations=locations or [],
        requested_by=user_id,
    )
    db.add(run)
    await db.commit()
    enqueue("trends.discover", run.id)
    return run


async def get_run(
    db: AsyncSession, organization_id: uuid.UUID, run_id: uuid.UUID
) -> TrendDiscoveryRun:
    run = await db.scalar(
        select(TrendDiscoveryRun).where(
            TrendDiscoveryRun.id == run_id, TrendDiscoveryRun.organization_id == organization_id
        )
    )
    if run is None:
        raise NotFound("Discovery run")
    return run


async def list_runs(
    db: AsyncSession, organization_id: uuid.UUID, limit: int
) -> list[TrendDiscoveryRun]:
    return list(
        await db.scalars(
            select(TrendDiscoveryRun)
            .where(TrendDiscoveryRun.organization_id == organization_id)
            .order_by(TrendDiscoveryRun.created_at.desc())
            .limit(limit)
        )
    )


STATUS_FILTERS = {
    "active": [TrendStatus.NEW, TrendStatus.ANALYZED],
    "shortlisted": [TrendStatus.SHORTLISTED],
    "rejected": [TrendStatus.REJECTED],
    "archived": [TrendStatus.ARCHIVED],
}


async def list_trends(
    db: AsyncSession,
    organization_id: uuid.UUID,
    *,
    status: str,
    source: str | None,
    location: str | None,
    q: str | None,
    min_score: float | None,
    sort: str,
    limit: int,
    offset: int,
    relevance: str | None = None,
) -> TrendPage:
    filters = [Trend.organization_id == organization_id]
    if status in STATUS_FILTERS:
        filters.append(Trend.status.in_(STATUS_FILTERS[status]))
    if source:
        filters.append(Trend.sources.contains([source]))
    if location:
        filters.append(Trend.locations.contains([location]))
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(Trend.topic.ilike(pattern) | cast(Trend.keywords, Text).ilike(pattern))
    if min_score is not None:
        filters.append(Trend.opportunity_score >= min_score)
    if relevance == "relevant":
        filters.append(
            Trend.relevance_level.in_([RelevanceLevel.HIGHLY_RELEVANT, RelevanceLevel.RELEVANT])
        )
    elif relevance == "unanalyzed":
        filters.append(Trend.relevance_level.is_(None))
    elif relevance:
        filters.append(Trend.relevance_level == RelevanceLevel(relevance))

    order = {
        "score": [nulls_last(Trend.opportunity_score.desc()), Trend.last_seen_at.desc()],
        "recent": [Trend.last_seen_at.desc()],
        "mentions": [Trend.mention_count.desc(), Trend.last_seen_at.desc()],
        "new": [Trend.first_seen_at.desc()],
    }[sort]
    total = await db.scalar(select(func.count()).select_from(Trend).where(*filters))
    rows = await db.scalars(
        select(Trend).where(*filters).order_by(*order).limit(limit).offset(offset)
    )
    return TrendPage(items=[TrendListItem.model_validate(t) for t in rows], total=total or 0)


async def _get_trend(db: AsyncSession, organization_id: uuid.UUID, trend_id: uuid.UUID) -> Trend:
    trend = await db.scalar(
        select(Trend).where(Trend.id == trend_id, Trend.organization_id == organization_id)
    )
    if trend is None:
        raise NotFound("Trend")
    return trend


async def trend_detail(
    db: AsyncSession, organization_id: uuid.UUID, trend_id: uuid.UUID
) -> TrendDetail:
    trend = await _get_trend(db, organization_id, trend_id)
    mentions = await db.scalars(
        select(TrendMention)
        .where(TrendMention.trend_id == trend.id)
        .order_by(
            nulls_last(TrendMention.engagement.desc()),
            nulls_last(TrendMention.published_at.desc()),
        )
        .limit(100)
    )
    job = await alignment.latest_job(db, trend.id)
    topic = await topic_sync.topic_for_trend(db, trend)
    return TrendDetail(
        **TrendListItem.model_validate(trend).model_dump(),
        alignment=trend.alignment,
        relevance_confidence=trend.relevance_confidence,
        analysis=AnalysisStatus(
            job_id=job.id,
            status=job.status,
            engine="ai" if job.provider not in (None, "rules") else "rules",
            error=job.error,
            created_at=job.created_at,
            completed_at=job.completed_at,
        )
        if job
        else None,
        mentions=[MentionRead.model_validate(m) for m in mentions],
        topic_id=topic.id if topic else None,
    )


async def request_analysis(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, trend_id: uuid.UUID
) -> AIGenerationJob:
    """Spec §38 POST /trends/{id}/analyze: (re)run alignment in the background."""
    trend = await _get_trend(db, organization_id, trend_id)
    job = await alignment.create_job(db, trend)
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.TREND_ANALYSIS_REQUESTED,
        entity_type="trend",
        entity_id=trend.id,
        new_value={"engine": job.provider},
    )
    await db.commit()
    enqueue("trends.align", job.id)
    return job


async def override_relevance(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    trend_id: uuid.UUID,
    level: RelevanceLevel | None,
) -> TrendDetail:
    trend = await _get_trend(db, organization_id, trend_id)
    await alignment.override_relevance(db, trend, level, user_id)
    await db.commit()
    return await trend_detail(db, organization_id, trend.id)


DELETABLE = (TrendStatus.SHORTLISTED, TrendStatus.REJECTED, TrendStatus.ARCHIVED)


async def delete_trend(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, trend_id: uuid.UUID
) -> None:
    """Permanently remove a shortlisted, rejected or archived trend with its
    mentions and its topic (whose plans go with it; written posts are kept)."""
    trend = await _get_trend(db, organization_id, trend_id)
    if trend.status not in DELETABLE:
        raise InvalidStateTransition(
            "Only shortlisted, rejected or archived trends can be deleted."
        )
    topic = await topic_sync.topic_for_trend(db, trend)
    if topic is not None:
        await db.delete(topic)
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=AuditAction.TREND_DELETED,
        entity_type="trend",
        entity_id=trend.id,
        old_value={"status": trend.status, "topic": trend.topic},
    )
    await db.delete(trend)
    await db.commit()


_ACTIONS = {
    TrendStatus.SHORTLISTED: AuditAction.TREND_SHORTLISTED,
    TrendStatus.REJECTED: AuditAction.TREND_REJECTED,
    TrendStatus.NEW: AuditAction.TREND_RESTORED,
    TrendStatus.ANALYZED: AuditAction.TREND_RESTORED,
}


async def transition(
    db: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    trend_id: uuid.UUID,
    target: TrendStatus,
) -> TrendDetail:
    trend = await _get_trend(db, organization_id, trend_id)
    if target == TrendStatus.NEW and trend.analyzed_at is not None:
        target = TrendStatus.ANALYZED  # restoring keeps the analysis
    TREND_MACHINE.assert_can(trend.status, target)
    previous = trend.status
    trend.status = target
    audit.record(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action=_ACTIONS[target],
        entity_type="trend",
        entity_id=trend.id,
        old_value={"status": previous},
        new_value={"status": target, "topic": trend.topic},
    )
    await topic_sync.on_trend_status(db, trend, target, user_id)
    await db.commit()
    return await trend_detail(db, organization_id, trend.id)
