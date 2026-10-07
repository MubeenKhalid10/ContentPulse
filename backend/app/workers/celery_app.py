"""Celery workers and beat (opt-in: TASK_BACKEND=celery).

    celery -A app.workers.celery_app worker --loglevel=info   (add --pool=solo on Windows)
    celery -A app.workers.celery_app beat --loglevel=info

Each worker process keeps one event loop and runs the same async job
functions the API uses in-process. Beat replaces the API's scheduler loop:
it triggers due trend discovery every minute and recovers interrupted jobs.
"""

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any

from celery import Celery
from celery.signals import worker_process_init
from sqlalchemy.exc import InterfaceError, OperationalError

from app.core.config import get_settings
from app.core.logging import configure_logging, logger
from app.workers.tasks import CELERY_PREFIX, JOBS, resolve

settings = get_settings()
configure_logging(settings.log_level)

celery_app = Celery("contentpulse", broker=settings.celery_broker_url or settings.redis_url)
celery_app.conf.update(
    # Jobs record their own results in Postgres.
    task_ignore_result=True,
    # Redeliver a job if its worker dies mid-run; jobs skip work they already did.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    timezone="UTC",
    beat_schedule={
        "schedule-trend-discovery": {
            "task": CELERY_PREFIX + "schedule_discovery",
            "schedule": 60.0,
        },
        "recover-interrupted-jobs": {
            "task": CELERY_PREFIX + "recover_stale_jobs",
            "schedule": 600.0,
        },
        "prune-request-history": {
            "task": CELERY_PREFIX + "prune_request_history",
            "schedule": 86400.0,
        },
    },
)

_loop: asyncio.AbstractEventLoop | None = None


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine on this worker process's persistent event loop (the
    database pool's connections belong to it)."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)


@worker_process_init.connect
def _fresh_pool(**_: Any) -> None:
    # Forked worker processes must not reuse the parent's database connections.
    from app.db.session import engine

    engine.sync_engine.dispose(close=False)


# Transient infrastructure errors before a job could record anything: retry.
TRANSIENT = (OperationalError, InterfaceError, ConnectionError, TimeoutError, OSError)


def _register(name: str) -> None:
    @celery_app.task(
        name=CELERY_PREFIX + name,
        autoretry_for=TRANSIENT,
        retry_backoff=10,
        retry_backoff_max=300,
        max_retries=5,
    )
    def job(entity_id: str) -> None:
        run_async(resolve(name)(uuid.UUID(entity_id)))


for _name in JOBS:
    _register(_name)


@celery_app.task(name=CELERY_PREFIX + "schedule_discovery")
def schedule_discovery() -> int:
    from app.workers.scheduler import schedule_due_runs

    scheduled = run_async(schedule_due_runs())
    if scheduled:
        logger.info("Scheduled %d trend discovery run(s)", scheduled)
    return scheduled


@celery_app.task(name=CELERY_PREFIX + "recover_stale_jobs")
def recover_stale_jobs() -> int:
    from app.services.alignment import service as alignment
    from app.workers import knowledge_tasks, trend_tasks

    async def recover() -> int:
        return (
            await knowledge_tasks.recover_stale_jobs()
            + await trend_tasks.recover_stale_runs()
            + await alignment.recover_stale_jobs()
        )

    recovered = run_async(recover())
    if recovered:
        logger.warning("Marked %d interrupted job(s) as failed", recovered)
    return recovered


@celery_app.task(name=CELERY_PREFIX + "prune_request_history")
def prune_request_history() -> int:
    from app.services.housekeeping import prune_llm_requests

    return run_async(prune_llm_requests())
