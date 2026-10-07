"""Organization alignment (spec §14-16): analyze trends, persist results,
record every AI call (spec §56), and let humans override (spec §16)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.provider import AIError, get_ai_provider
from app.core.config import get_settings
from app.core.errors import NotFound
from app.core.logging import logger
from app.db.session import SessionLocal
from app.models.ai import AIGenerationJob
from app.models.enums import JobStatus, RelevanceLevel, TrendStatus
from app.models.trend import Trend
from app.services import audit
from app.services.alignment.context import load_context
from app.services.alignment.engines import (
    align_with_ai,
    align_with_rules,
    retrieve_passages,
    top_mentions,
)
from app.services.alignment.result import AlignmentResult
from app.services.audit import AuditAction
from app.services.topics import sync as topic_sync
from app.services.trends.scoring import opportunity
from app.services.workflow import TREND_MACHINE
from app.workers.tasks import schedule_retry

JOB_TYPE = "trend_alignment"
STALE_AFTER = timedelta(minutes=15)
LEVEL_LABELS = {
    RelevanceLevel.HIGHLY_RELEVANT: "Highly relevant",
    RelevanceLevel.RELEVANT: "Relevant",
    RelevanceLevel.WEAKLY_RELEVANT: "Weakly relevant",
    RelevanceLevel.NOT_RELEVANT: "Not relevant",
}


def _now() -> datetime:
    return datetime.now(UTC)


async def active_job(db: AsyncSession, trend_id: uuid.UUID) -> AIGenerationJob | None:
    return await db.scalar(
        select(AIGenerationJob).where(
            AIGenerationJob.entity_id == trend_id,
            AIGenerationJob.type == JOB_TYPE,
            AIGenerationJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            AIGenerationJob.created_at >= _now() - STALE_AFTER,
        )
    )


async def latest_job(db: AsyncSession, trend_id: uuid.UUID) -> AIGenerationJob | None:
    return await db.scalar(
        select(AIGenerationJob)
        .where(AIGenerationJob.entity_id == trend_id, AIGenerationJob.type == JOB_TYPE)
        .order_by(AIGenerationJob.created_at.desc())
        .limit(1)
    )


async def create_job(db: AsyncSession, trend: Trend) -> AIGenerationJob:
    """Queue analysis for one trend; reuse an in-flight job if there is one."""
    existing = await active_job(db, trend.id)
    if existing:
        return existing
    provider = get_ai_provider(workflow=JOB_TYPE)
    job = AIGenerationJob(
        organization_id=trend.organization_id,
        type=JOB_TYPE,
        entity_type="trend",
        entity_id=trend.id,
        provider=provider.name if provider else "rules",
        model=provider.model if provider else None,
    )
    db.add(job)
    await db.flush()
    return job


def _apply(trend: Trend, result: AlignmentResult, alignment: dict) -> None:
    trend.alignment = alignment
    trend.analyzed_at = _now()
    if not trend.relevance_overridden:
        trend.relevance_level = result.classification
        trend.relevance_confidence = result.confidence
    label = LEVEL_LABELS[result.classification]
    prefix = "AI" if result.engine == "ai" else "Rule-based estimate"
    signals = dict(trend.signals)
    signals["organization_fit"] = {
        "score": result.organization_fit,
        "detail": f"{prefix}: {label.lower()}",
    }
    if result.audience_relevance is not None:
        signals["audience_relevance"] = {
            "score": result.audience_relevance,
            "detail": "AI estimate of interest among your target audience",
        }
    else:
        signals.pop("audience_relevance", None)
    trend.signals = signals
    trend.opportunity_score = opportunity(signals)
    if TREND_MACHINE.can(trend.status, TrendStatus.ANALYZED) and trend.status == TrendStatus.NEW:
        trend.status = TrendStatus.ANALYZED


async def run_job(job_id: uuid.UUID) -> None:
    """Execute one alignment job. Failures are recorded, never raised."""
    async with SessionLocal() as db:
        job = await db.get(AIGenerationJob, job_id)
        if job is None or job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            return
        job.status = JobStatus.RUNNING
        job.attempts += 1
        await db.commit()

        try:
            trend = await db.get(Trend, job.entity_id)
            if trend is None:
                raise NotFound("Trend")
            ctx = await load_context(db, trend.organization_id)
            mentions = await top_mentions(db, trend.id)
            passages = await retrieve_passages(db, trend.organization_id, trend)
            provider = get_ai_provider(workflow=JOB_TYPE)
            meta: dict = {"job_id": str(job.id)}
            if provider is not None:
                prompt = prompts.load("organization_alignment")
                job.prompt_template_id = await prompts.register(db, prompt, provider.model)
                result, raw = await align_with_ai(
                    provider, ctx, trend, mentions, passages, job_id=job.id
                )
                job.provider, job.model = raw.provider, raw.model
                job.input_tokens, job.output_tokens = raw.input_tokens, raw.output_tokens
                meta |= {
                    "model": raw.model,
                    "prompt": {"name": prompt.name, "version": prompt.version},
                }
            else:
                result = align_with_rules(ctx, trend, mentions, passages)
                job.provider, job.model = "rules", None
            alignment = result.to_json(passages, analyzed_at=_now().isoformat(), **meta)
            _apply(trend, result, alignment)
            await topic_sync.sync_from_trend(db, trend)
            job.status = JobStatus.SUCCEEDED
            job.result = {
                "classification": result.classification.value,
                "organization_fit": result.organization_fit,
                "corrections": result.corrections,
            }
        except AIError as exc:
            await db.rollback()
            job = await db.get(AIGenerationJob, job_id)
            assert job is not None
            if await schedule_retry(db, job, exc, "trends.align"):
                return
            logger.warning("Alignment job %s failed: %s", job_id, exc.message)
            job.status = JobStatus.FAILED
            job.error = exc.user_message
            job.result = {"error_kind": exc.kind.value}
        except Exception:
            logger.exception("Alignment job %s crashed", job_id)
            await db.rollback()
            job = await db.get(AIGenerationJob, job_id)
            assert job is not None
            job.status = JobStatus.FAILED
            job.error = "Analysis failed unexpectedly."
        job.completed_at = _now()
        await db.commit()


async def analyze_organization(organization_id: uuid.UUID) -> int:
    """Analyze recent trends that need it (after each discovery run).

    AI analysis covers the top trends by opportunity (a cost guard); the free
    rule-based engine covers all of them when no LLM is configured.
    """
    settings = get_settings()
    ai = get_ai_provider(workflow=JOB_TYPE) is not None
    limit = settings.alignment_ai_batch_size if ai else 200
    async with SessionLocal() as db:
        needs = [Trend.analyzed_at.is_(None)]
        if ai:  # upgrade earlier rule-based estimates once AI is available
            needs.append(Trend.alignment["engine"].astext == "rules")
        trends = list(
            await db.scalars(
                select(Trend)
                .where(
                    Trend.organization_id == organization_id,
                    Trend.status.in_(
                        [TrendStatus.NEW, TrendStatus.ANALYZED, TrendStatus.SHORTLISTED]
                    ),
                    Trend.last_seen_at >= _now() - timedelta(days=7),
                    or_(*needs),
                )
                .order_by(Trend.opportunity_score.desc().nulls_last())
                .limit(limit)
            )
        )
        jobs = [await create_job(db, t) for t in trends]
        await db.commit()
        job_ids = [j.id for j in jobs]

    # Bounds this process's open sessions; the gateway's shared quotas decide
    # how many requests actually reach the provider.
    semaphore = asyncio.Semaphore(max(1, settings.llm_max_concurrency))

    async def bounded(job_id: uuid.UUID) -> None:
        async with semaphore:
            await run_job(job_id)

    await asyncio.gather(*(bounded(j) for j in job_ids))
    return len(job_ids)


async def override_relevance(
    db: AsyncSession,
    trend: Trend,
    level: RelevanceLevel | None,
    user_id: uuid.UUID,
) -> None:
    """Human override (spec §16). `None` returns control to the analysis."""
    previous = trend.relevance_level
    if level is None:
        trend.relevance_overridden = False
        recorded = trend.alignment.get("classification") if trend.alignment else None
        trend.relevance_level = RelevanceLevel(recorded) if recorded else None
    else:
        trend.relevance_overridden = True
        trend.relevance_level = level
    audit.record(
        db,
        organization_id=trend.organization_id,
        user_id=user_id,
        action=AuditAction.TREND_RELEVANCE_OVERRIDDEN,
        entity_type="trend",
        entity_id=trend.id,
        old_value={"relevance_level": previous},
        new_value={
            "relevance_level": trend.relevance_level,
            "overridden": trend.relevance_overridden,
        },
    )
    await topic_sync.sync_from_trend(db, trend)


async def recover_stale_jobs() -> int:
    async with SessionLocal() as db:
        result = await db.execute(
            update(AIGenerationJob)
            .where(
                AIGenerationJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                AIGenerationJob.created_at < _now() - STALE_AFTER,
            )
            .values(
                status=JobStatus.FAILED,
                error="Interrupted: the server restarted.",
                completed_at=_now(),
            )
        )
        await db.commit()
        return result.rowcount or 0
