"""Periodic trend discovery (spec §45, §46).

Each organization's `trend_frequency` decides when collection runs: hourly,
every 3 hours (the default for new organizations), every 6 hours, or daily at
08:00 in the organization's timezone (so the morning dashboard is fresh).

The scheduler *tick* only checks which organizations are due; it never
refreshes providers by itself. Ticks come from the in-process loop below (every
TREND_SCHEDULER_TICK_SECONDS while the API is awake) and can also come from an
external trigger. Duplicate or concurrent ticks are harmless: a Postgres
advisory lock lets one tick schedule at a time, and a unique index allows at
most one queued/running run per organization.
"""

import asyncio
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from app.ai.metrics import metrics
from app.core.config import get_settings
from app.core.logging import logger
from app.db.session import SessionLocal
from app.models.enums import DiscoveryRunStatus, RunTrigger, TrendFrequency
from app.models.organization import Organization, OrganizationSettings
from app.models.trend import TrendDiscoveryRun
from app.workers.tasks import enqueue

DAILY_AT = time(8, 0)
LOCK_ID = 7_302_514  # arbitrary, unique to this scheduler
INTERVALS = {
    TrendFrequency.HOURLY: timedelta(hours=1),
    TrendFrequency.EVERY_3_HOURS: timedelta(hours=3),
    TrendFrequency.EVERY_6_HOURS: timedelta(hours=6),
}
ACTIVE = (DiscoveryRunStatus.QUEUED, DiscoveryRunStatus.RUNNING)
# Literal predicate of uq_trend_discovery_runs_one_active (ON CONFLICT must
# repeat it to pick the partial index; bound parameters don't match).
ACTIVE_PREDICATE = "status IN ('queued', 'running')"


def is_due(
    frequency: TrendFrequency,
    last_run: datetime | None,
    now: datetime,
    timezone: str,
    *,
    grace: timedelta = timedelta(0),
    failed_streak: int = 0,
    retry_delay: timedelta | None = None,
    max_retries: int = 0,
) -> bool:
    """Whether an organization should collect now.

    `failed_streak` counts the latest runs that failed in a row (an interrupted
    run counts as failed). The first `max_retries` of them are retried after
    `retry_delay`; after that the normal frequency applies again.
    """
    if frequency == TrendFrequency.MANUAL:
        return False
    if last_run is None:
        return True
    if (
        retry_delay is not None
        and 0 < failed_streak <= max_retries
        and now - last_run >= retry_delay
    ):
        return True
    if frequency in INTERVALS:
        return now - last_run >= INTERVALS[frequency] - min(grace, INTERVALS[frequency] / 2)
    # Daily: once per day, at or after 08:00 local time.
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    local_now = now.astimezone(tz)
    today_slot = datetime.combine(local_now.date(), DAILY_AT, tzinfo=tz)
    slot = today_slot if local_now >= today_slot else today_slot - timedelta(days=1)
    return last_run < slot.astimezone(UTC)


async def _failed_streaks(db, limit: int) -> dict[uuid.UUID, int]:
    """Consecutive failed runs at the head of each organization's history
    (only the latest `limit` runs are looked at)."""
    ranked = select(
        TrendDiscoveryRun.organization_id,
        TrendDiscoveryRun.status,
        func.row_number()
        .over(
            partition_by=TrendDiscoveryRun.organization_id,
            order_by=TrendDiscoveryRun.created_at.desc(),
        )
        .label("rn"),
    ).subquery()
    rows = await db.execute(
        select(ranked.c.organization_id, ranked.c.status)
        .where(ranked.c.rn <= limit)
        .order_by(ranked.c.organization_id, ranked.c.rn)
    )
    streaks: dict[uuid.UUID, int] = {}
    broken: set[uuid.UUID] = set()
    for org_id, status in rows:
        if org_id in broken:
            continue
        if status == DiscoveryRunStatus.FAILED:
            streaks[org_id] = streaks.get(org_id, 0) + 1
        else:
            broken.add(org_id)
    return streaks


async def schedule_due_runs(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    settings = get_settings()
    async with SessionLocal() as db:
        locked = await db.scalar(select(func.pg_try_advisory_xact_lock(LOCK_ID)))
        if not locked:
            return 0
        last_run = (
            select(
                TrendDiscoveryRun.organization_id,
                func.max(TrendDiscoveryRun.created_at).label("last_run"),
                func.count().filter(TrendDiscoveryRun.status.in_(ACTIVE)).label("active"),
            )
            .group_by(TrendDiscoveryRun.organization_id)
            .subquery()
        )
        rows = await db.execute(
            select(
                OrganizationSettings.organization_id,
                OrganizationSettings.trend_frequency,
                OrganizationSettings.enabled_sources,
                OrganizationSettings.target_markets,
                Organization.timezone,
                last_run.c.last_run,
                last_run.c.active,
            )
            .join(Organization, Organization.id == OrganizationSettings.organization_id)
            .outerjoin(last_run, last_run.c.organization_id == OrganizationSettings.organization_id)
            .where(OrganizationSettings.trend_frequency != TrendFrequency.MANUAL)
        )
        streaks = await _failed_streaks(db, settings.trend_failure_max_retries + 1)
        created: list[uuid.UUID] = []
        for org_id, frequency, sources, markets, tz, last, active in rows:
            due = is_due(
                frequency,
                last,
                now,
                tz,
                grace=timedelta(seconds=settings.trend_schedule_grace_seconds),
                failed_streak=streaks.get(org_id, 0),
                retry_delay=timedelta(minutes=settings.trend_failure_retry_minutes),
                max_retries=settings.trend_failure_max_retries,
            )
            if active or not sources or not due:
                continue
            # A manual run started meanwhile wins: the unique index on active
            # runs turns this insert into a no-op instead of a second run.
            run_id = await db.scalar(
                insert(TrendDiscoveryRun)
                .values(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    status=DiscoveryRunStatus.QUEUED,
                    trigger=RunTrigger.SCHEDULED,
                    sources=list(sources),
                    locations=list(markets),
                )
                .on_conflict_do_nothing(
                    index_elements=["organization_id"],
                    index_where=text(ACTIVE_PREDICATE),
                )
                .returning(TrendDiscoveryRun.id)
            )
            if run_id is not None:
                created.append(run_id)
        await db.commit()
    for run_id in created:
        enqueue("trends.discover", run_id)
    return len(created)


async def tick(now: datetime | None = None) -> dict[str, int]:
    """One scheduler pass: close runs that stopped responding (so they can be
    retried and don't block their organization), then start due runs."""
    from app.workers import trend_tasks

    recovered = await trend_tasks.recover_stale_runs()
    scheduled = await schedule_due_runs(now)
    metrics.inc("trend_scheduler_stale_runs_total", recovered)
    metrics.inc("trend_scheduler_runs_started_total", scheduled)
    return {"recovered": recovered, "scheduled": scheduled}


HOUSEKEEPING_EVERY = timedelta(hours=1)


async def scheduler_loop() -> None:
    from app.services.housekeeping import run_housekeeping

    last_housekeeping: datetime | None = None
    while True:
        try:
            result = await tick()
            if result["scheduled"] or result["recovered"]:
                logger.info(
                    "Trend scheduler: %d run(s) started, %d stale run(s) closed",
                    result["scheduled"],
                    result["recovered"],
                )
        except Exception:
            logger.exception("Trend scheduler tick failed")
        now = datetime.now(UTC)
        if last_housekeeping is None or now - last_housekeeping >= HOUSEKEEPING_EVERY:
            last_housekeeping = now
            try:
                await run_housekeeping(now)
            except Exception:
                logger.exception("Housekeeping failed")
        await asyncio.sleep(get_settings().trend_scheduler_tick_seconds)
