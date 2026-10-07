"""Background job dispatch (spec rule 6, §44).

Every job is a named async function taking one id. `enqueue` runs it in the
API process (TASK_BACKEND=inprocess, the default) or hands it to a Celery
worker (TASK_BACKEND=celery). Job state always lives in the database, so the
two backends behave the same and the UI never knows which one ran the job.
"""

import asyncio
import importlib
import math
import uuid
from collections.abc import Awaitable, Callable

from app.core.config import get_settings
from app.core.logging import logger
from app.workers.runner import runner

# name -> "module:function". Resolved lazily to avoid import cycles.
JOBS: dict[str, str] = {
    "knowledge.crawl": "app.workers.knowledge_tasks:run_crawl_job",
    "knowledge.reindex": "app.workers.knowledge_tasks:run_reindex_job",
    "trends.discover": "app.workers.trend_tasks:run_discovery",
    "trends.align": "app.services.alignment.service:run_job",
    "trends.align_organization": "app.services.alignment.service:analyze_organization",
    "content.generate": "app.services.content.generation:run",
    "design.brief": "app.services.design.briefs:run_ai_brief",
    "design.image": "app.services.design.images:run",
}
CELERY_PREFIX = "contentpulse."


def resolve(name: str) -> Callable[[uuid.UUID], Awaitable[object]]:
    module, func = JOBS[name].split(":")
    return getattr(importlib.import_module(module), func)


async def _delayed(name: str, entity_id: uuid.UUID, delay: float) -> None:
    await asyncio.sleep(delay)
    await resolve(name)(entity_id)


def _run_inprocess(name: str, entity_id: uuid.UUID, countdown: float) -> None:
    coro = _delayed(name, entity_id, countdown) if countdown else resolve(name)(entity_id)
    runner.submit(coro, name=f"{name}:{entity_id}")


def enqueue(name: str, entity_id: uuid.UUID, *, countdown: float = 0) -> None:
    """Run job `name` for `entity_id`. Call after committing the job's row."""
    if name not in JOBS:
        raise KeyError(f"Unknown job {name!r}")
    if get_settings().task_backend == "celery":
        from app.workers.celery_app import celery_app

        try:
            celery_app.send_task(
                CELERY_PREFIX + name, args=[str(entity_id)], countdown=countdown or None
            )
            return
        except Exception:
            # The broker is down: run here rather than lose the job.
            logger.exception("Could not queue %s on Celery; running it in-process", name)
    _run_inprocess(name, entity_id, countdown)


def retry_delay(attempts: int) -> int | None:
    """Seconds before retry number `attempts` (1-based), or None when exhausted."""
    delays = get_settings().job_retry_delays
    return delays[attempts - 1] if 0 < attempts <= len(delays) else None


async def schedule_retry(db, job, exc, name: str) -> bool:
    """Spec §56: a rate limit or outage re-queues the AI job with backoff
    instead of failing it. Returns False when the error is permanent or the
    retries are used up (the caller then records the failure)."""
    from app.ai.provider import QUEUED_MESSAGE
    from app.models.enums import JobStatus

    delay = retry_delay(job.attempts) if exc.retryable else None
    if delay is None:
        return False
    if exc.retry_after:  # never retry sooner than the provider asked (within reason)
        delay = max(delay, min(3600, math.ceil(exc.retry_after)))
    job.status = JobStatus.QUEUED
    job.error = QUEUED_MESSAGE
    job.result = {**(job.result or {}), "error_kind": exc.kind.value, "retries": job.attempts}
    await db.commit()
    logger.warning("%s job %s: %s; retry %d in %ds", name, job.id, exc.message, job.attempts, delay)
    enqueue(name, job.id, countdown=delay)
    return True
