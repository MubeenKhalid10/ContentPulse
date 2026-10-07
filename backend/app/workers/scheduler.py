"""Periodic trend discovery (spec §45, §46).

Each organization's `trend_frequency` decides when collection runs: hourly,
every 6 hours, or daily at 08:00 in the organization's timezone (so the
morning dashboard is fresh). A Postgres advisory lock makes sure only one API
instance schedules at a time. Celery beat replaces this loop in Sprint 9.
"""

import asyncio
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select

from app.core.logging import logger
from app.db.session import SessionLocal
from app.models.enums import DiscoveryRunStatus, RunTrigger, TrendFrequency
from app.models.organization import Organization, OrganizationSettings
from app.models.trend import TrendDiscoveryRun
from app.workers.tasks import enqueue

TICK_SECONDS = 60
DAILY_AT = time(8, 0)
LOCK_ID = 7_302_514  # arbitrary, unique to this scheduler
INTERVALS = {
    TrendFrequency.HOURLY: timedelta(hours=1),
    TrendFrequency.EVERY_6_HOURS: timedelta(hours=6),
}


def is_due(
    frequency: TrendFrequency, last_run: datetime | None, now: datetime, timezone: str
) -> bool:
    if frequency == TrendFrequency.MANUAL:
        return False
    if last_run is None:
        return True
    if frequency in INTERVALS:
        return now - last_run >= INTERVALS[frequency]
    # Daily: once per day, at or after 08:00 local time.
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    local_now = now.astimezone(tz)
    today_slot = datetime.combine(local_now.date(), DAILY_AT, tzinfo=tz)
    slot = today_slot if local_now >= today_slot else today_slot - timedelta(days=1)
    return last_run < slot.astimezone(UTC)


async def schedule_due_runs(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    async with SessionLocal() as db:
        locked = await db.scalar(select(func.pg_try_advisory_xact_lock(LOCK_ID)))
        if not locked:
            return 0
        last_run = (
            select(
                TrendDiscoveryRun.organization_id,
                func.max(TrendDiscoveryRun.created_at).label("last_run"),
                func.count()
                .filter(
                    TrendDiscoveryRun.status.in_(
                        [DiscoveryRunStatus.QUEUED, DiscoveryRunStatus.RUNNING]
                    )
                )
                .label("active"),
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
        created: list[TrendDiscoveryRun] = []
        for org_id, frequency, sources, markets, tz, last, active in rows:
            if active or not sources or not is_due(frequency, last, now, tz):
                continue
            run = TrendDiscoveryRun(
                organization_id=org_id,
                trigger=RunTrigger.SCHEDULED,
                sources=list(sources),
                locations=list(markets),
            )
            db.add(run)
            created.append(run)
        await db.commit()
    for run in created:
        enqueue("trends.discover", run.id)
    return len(created)


HOUSEKEEPING_EVERY = timedelta(days=1)


async def scheduler_loop() -> None:
    from app.services.housekeeping import prune_llm_requests

    last_housekeeping: datetime | None = None
    while True:
        try:
            scheduled = await schedule_due_runs()
            if scheduled:
                logger.info("Scheduled %d trend discovery run(s)", scheduled)
        except Exception:
            logger.exception("Trend scheduler tick failed")
        now = datetime.now(UTC)
        if last_housekeeping is None or now - last_housekeeping >= HOUSEKEEPING_EVERY:
            last_housekeeping = now
            try:
                await prune_llm_requests(now)
            except Exception:
                logger.exception("Housekeeping failed")
        await asyncio.sleep(TICK_SECONDS)
