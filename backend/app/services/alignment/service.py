"""Organization alignment (spec §14-16): analyze trends, persist results,
record every AI call (spec §56), and let humans override (spec §16)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import prompts
from app.ai.provider import AIError, AIErrorKind, get_ai_provider
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
# The model's answer, not its availability, failed: asking again with the same
# trend coverage gives the same result, so automatic runs stop retrying it.
FINAL_FAILURES = frozenset(
    {
        AIErrorKind.BAD_OUTPUT.value,
        AIErrorKind.REFUSED.value,
        AIErrorKind.BAD_REQUEST.value,
        AIErrorKind.OVERSIZED.value,
    }
)
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


async def create_job(db: AsyncSession, trend: Trend, *, auto: bool = False) -> AIGenerationJob:
    """Queue analysis for one trend; reuse an in-flight job if there is one.

    `auto` jobs (after discovery) only reach the LLM when the rule engine finds
    a signal (ALIGNMENT_AI_GATE); someone asking for analysis always gets AI."""
    existing = await active_job(db, trend.id)
    if existing:
        if not auto and existing.result.get("auto"):
            existing.result = {**existing.result, "auto": False}
        return existing
    provider = get_ai_provider(workflow=JOB_TYPE)
    job = AIGenerationJob(
        organization_id=trend.organization_id,
        type=JOB_TYPE,
        entity_type="trend",
        entity_id=trend.id,
        provider=provider.name if provider else "rules",
        model=provider.model if provider else None,
        result={"auto": True} if auto else {},
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
            gated = None
            if provider is not None and job.result.get("auto") and get_settings().alignment_ai_gate:
                rules = align_with_rules(ctx, trend, mentions, passages)
                if not has_signal(rules):
                    # No keyword, service or knowledge connection: the free
                    # estimate stands, until the trend's coverage changes.
                    gated = rules
                    meta |= {"ai_gate": "no_signal", "mention_count": trend.mention_count}
            if gated is not None:
                result = gated
                job.provider, job.model = "rules", None
            elif provider is not None:
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
                **job.result,
                "classification": result.classification.value,
                "organization_fit": result.organization_fit,
                "corrections": result.corrections,
                **({"ai_gate": "no_signal"} if gated is not None else {}),
            }
        except AIError as exc:
            await db.rollback()
            job = await db.get(AIGenerationJob, job_id)
            assert job is not None
            if await schedule_retry(db, job, exc, "trends.align"):
                return
            logger.warning("Alignment job %s failed: %s", job_id, exc.message)
            trend = await db.get(Trend, job.entity_id)
            job.status = JobStatus.FAILED
            job.error = exc.user_message
            # mention_count identifies the coverage the failure applies to.
            job.result = {
                **job.result,
                "error_kind": exc.kind.value,
                "mention_count": trend.mention_count if trend else None,
            }
        except Exception:
            logger.exception("Alignment job %s crashed", job_id)
            await db.rollback()
            job = await db.get(AIGenerationJob, job_id)
            assert job is not None
            job.status = JobStatus.FAILED
            job.error = "Analysis failed unexpectedly."
        job.completed_at = _now()
        await db.commit()


def has_signal(rules: AlignmentResult) -> bool:
    """The rule engine found a keyword, service or knowledge connection (its
    baseline fit of 10 means none)."""
    return rules.organization_fit > 10


async def failure_hold(
    db: AsyncSession, trends: list[Trend], *, now: datetime | None = None
) -> set[uuid.UUID]:
    """Trends automatic analysis should skip for now, after failed AI runs.

    Counts the failures since the trend's last success. A final failure
    (refused or unusable answer) holds the trend until its coverage
    (mention_count) changes; others back off base x 2^(n-1) hours, and the
    trend is left alone after ALIGNMENT_MAX_FAILURES (a person can still ask
    for analysis)."""
    if not trends:
        return set()
    settings = get_settings()
    now = now or _now()
    jobs = await db.execute(
        select(
            AIGenerationJob.entity_id,
            AIGenerationJob.status,
            AIGenerationJob.result,
            AIGenerationJob.completed_at,
        )
        .where(
            AIGenerationJob.type == JOB_TYPE,
            AIGenerationJob.entity_id.in_([t.id for t in trends]),
            AIGenerationJob.status.in_([JobStatus.SUCCEEDED, JobStatus.FAILED]),
        )
        .order_by(AIGenerationJob.created_at.desc())
    )
    history: dict[uuid.UUID, list] = {}
    for row in jobs:
        history.setdefault(row.entity_id, []).append(row)
    held: set[uuid.UUID] = set()
    for trend in trends:
        failures = []
        for row in history.get(trend.id, []):  # newest first
            if row.status == JobStatus.SUCCEEDED:
                break
            failures.append(row)
        if not failures:
            continue
        latest = failures[0]
        result = latest.result or {}
        if result.get("error_kind") in FINAL_FAILURES:
            # Same coverage: same answer. New coverage: try again now.
            if result.get("mention_count") in (None, trend.mention_count):
                held.add(trend.id)
            continue
        if len(failures) >= settings.alignment_max_failures:
            held.add(trend.id)
            continue
        wait = timedelta(hours=settings.alignment_failure_backoff_hours * 2 ** (len(failures) - 1))
        if latest.completed_at and latest.completed_at + wait > now:
            held.add(trend.id)
    return held


def ai_priority():
    """Order for the limited AI batch: opportunity plus keyword fit (both
    0-100), so a viral trend unrelated to the organization doesn't outrank a
    smaller one that matches its keywords, services or industry. Missing
    scores count as 0; nothing is excluded, only ordered."""
    fit = func.coalesce(Trend.signals["keyword_match"]["score"].as_float(), 0.0)
    return func.coalesce(Trend.opportunity_score, 0.0) + fit


async def analyze_organization(organization_id: uuid.UUID) -> int:
    """Analyze recent trends that need it (after each discovery run).

    AI analysis covers the top trends by opportunity and fit (a cost guard); the free
    rule-based engine covers all of them when no LLM is configured.
    """
    settings = get_settings()
    ai = get_ai_provider(workflow=JOB_TYPE) is not None
    limit = settings.alignment_ai_batch_size if ai else 200
    async with SessionLocal() as db:
        needs = [Trend.analyzed_at.is_(None)]
        if ai:  # upgrade earlier rule-based estimates once AI is available
            # ...except ones the gate kept from the LLM, until new coverage.
            gate_count = Trend.alignment["mention_count"].as_integer()
            needs.append(
                (Trend.alignment["engine"].astext == "rules")
                & (
                    Trend.alignment["ai_gate"].astext.is_(None)
                    | gate_count.is_(None)
                    | (gate_count != Trend.mention_count)
                )
            )
        candidates = list(
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
                .order_by(ai_priority().desc(), Trend.last_seen_at.desc())
                # Room for the trends held back after failures.
                .limit(limit * 3 if ai else limit)
            )
        )
        held = await failure_hold(db, candidates) if ai else set()
        trends = [t for t in candidates if t.id not in held][:limit]
        jobs = [await create_job(db, t, auto=True) for t in trends]
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
