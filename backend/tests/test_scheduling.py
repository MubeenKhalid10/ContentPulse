"""Three-hour default cadence, retries after failures, and one active run per
organization under concurrent manual and scheduled triggers."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.models.enums import DiscoveryRunStatus, RunTrigger, TrendFrequency
from app.models.trend import TrendDiscoveryRun
from app.workers import scheduler
from app.workers.runner import runner
from tests.conftest import create_org, register
from tests.test_trends_api import API, internet, setup  # noqa: F401  (fixture)

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
GRACE = timedelta(minutes=10)


@pytest.mark.parametrize(
    ("minutes_since", "expected"),
    [(120, False), (165, False), (172, True), (180, True), (200, True)],
)
def test_three_hour_interval_with_tick_grace(minutes_since, expected):
    last = NOW - timedelta(minutes=minutes_since)
    assert scheduler.is_due(TrendFrequency.EVERY_3_HOURS, last, NOW, "UTC", grace=GRACE) is expected


def test_grace_never_halves_short_intervals_away():
    last = NOW - timedelta(minutes=25)
    # Hourly with a large grace still waits at least half the interval.
    assert not scheduler.is_due(TrendFrequency.HOURLY, last, NOW, "UTC", grace=timedelta(hours=2))


def test_failed_runs_retry_a_bounded_number_of_times():
    last = NOW - timedelta(minutes=31)
    kw = {"retry_delay": timedelta(minutes=30), "max_retries": 2}
    due = scheduler.is_due
    assert due(TrendFrequency.DAILY, last, NOW, "UTC", failed_streak=1, **kw)
    assert due(TrendFrequency.EVERY_3_HOURS, last, NOW, "UTC", failed_streak=2, **kw)
    # Too soon after the failure.
    soon = NOW - timedelta(minutes=10)
    assert not due(TrendFrequency.EVERY_3_HOURS, soon, NOW, "UTC", failed_streak=1, **kw)
    # Retries used up: back to the normal 3-hour cadence.
    assert not due(TrendFrequency.EVERY_3_HOURS, last, NOW, "UTC", failed_streak=3, **kw)
    later = NOW - timedelta(hours=3)
    assert due(TrendFrequency.EVERY_3_HOURS, later, NOW, "UTC", failed_streak=3, **kw)
    # Manual never runs on a schedule, failures or not.
    assert not due(TrendFrequency.MANUAL, last, NOW, "UTC", failed_streak=1, **kw)


async def test_new_organizations_default_to_three_hours_and_custom_choices_stay(client):
    admin, org = await setup(client)
    url = f"/api/v1/organizations/{org['id']}/settings"
    assert (await admin.get(url)).json()["trend_frequency"] == "every_3_hours"
    for choice in ("daily", "hourly", "every_6_hours", "manual", "every_3_hours"):
        resp = await admin.patch(url, json={"trend_frequency": choice})
        assert resp.status_code == 200 and resp.json()["trend_frequency"] == choice


async def test_scheduler_follows_each_organizations_frequency(client, db, monkeypatch):
    monkeypatch.setattr(runner, "submit", lambda coro, name: coro.close())
    admin, org = await setup(client)  # every 3 hours
    other = await register(client, "daily@b.example.com")
    org_b = await create_org(other, "Daily Co")
    await other.patch(
        f"/api/v1/organizations/{org_b['id']}/settings", json={"trend_frequency": "manual"}
    )
    assert await scheduler.schedule_due_runs() == 1  # the manual org is never scheduled

    # Pretend that run finished 2h ago: not due yet; 3h ago: due again.
    async def age(hours: float, status=DiscoveryRunStatus.SUCCEEDED):
        await db.execute(
            update(TrendDiscoveryRun).values(
                status=status, created_at=datetime.now(UTC) - timedelta(hours=hours)
            )
        )
        await db.commit()

    await age(2)
    assert await scheduler.schedule_due_runs() == 0
    await age(2.9)  # within the 10-minute grace of a tick
    assert await scheduler.schedule_due_runs() == 1


async def test_failed_scheduled_run_is_retried_then_backs_off(client, db, monkeypatch):
    monkeypatch.setattr(runner, "submit", lambda coro, name: coro.close())
    await setup(client)
    for expected in (1, 1, 1, 0):  # first run, then 2 retries, then normal cadence
        await db.execute(
            update(TrendDiscoveryRun)
            .where(TrendDiscoveryRun.status.in_(scheduler.ACTIVE))
            .values(
                status=DiscoveryRunStatus.FAILED,
                created_at=datetime.now(UTC) - timedelta(minutes=31),
            )
        )
        await db.commit()
        assert await scheduler.schedule_due_runs() == expected


async def test_tick_closes_stale_runs_so_the_organization_is_not_stuck(client, db, monkeypatch):
    monkeypatch.setattr(runner, "submit", lambda coro, name: coro.close())
    await setup(client)
    assert await scheduler.schedule_due_runs() == 1
    # The server slept mid-run: the run stopped heartbeating 20 minutes ago.
    stale = datetime.now(UTC) - timedelta(minutes=40)
    await db.execute(
        update(TrendDiscoveryRun).values(
            status=DiscoveryRunStatus.RUNNING, created_at=stale, heartbeat_at=stale
        )
    )
    await db.commit()
    result = await scheduler.tick()
    assert result == {"recovered": 1, "scheduled": 1}  # closed, then retried
    statuses = sorted((await db.scalars(select(TrendDiscoveryRun.status))).all())
    assert statuses == ["failed", "queued"]


async def test_database_allows_one_active_run_per_organization(client, db):
    _, org = await setup(client)
    org_id = uuid.UUID(org["id"])
    db.add(TrendDiscoveryRun(organization_id=org_id, trigger=RunTrigger.MANUAL))
    await db.commit()
    db.add(TrendDiscoveryRun(organization_id=org_id, trigger=RunTrigger.SCHEDULED))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
    # Finished runs don't count.
    db.add(
        TrendDiscoveryRun(
            organization_id=org_id,
            trigger=RunTrigger.SCHEDULED,
            status=DiscoveryRunStatus.SUCCEEDED,
        )
    )
    await db.commit()


async def test_concurrent_manual_and_scheduled_triggers_start_one_run(
    client,
    db,
    monkeypatch,
    internet,  # noqa: F811
):
    monkeypatch.setattr(runner, "submit", lambda coro, name: coro.close())
    admin, _ = await setup(client)
    results = await asyncio.gather(
        admin.post(f"{API}/discover", json={}),
        admin.post(f"{API}/discover", json={}),
        scheduler.schedule_due_runs(),
        scheduler.tick(),
        return_exceptions=True,
    )
    assert not [r for r in results if isinstance(r, BaseException)], results
    active = await db.scalar(
        select(func.count())
        .select_from(TrendDiscoveryRun)
        .where(TrendDiscoveryRun.status.in_(scheduler.ACTIVE))
    )
    assert active == 1
    codes = sorted(r.status_code for r in results[:2])
    assert codes in ([202, 409], [409, 409])  # 409 twice if the scheduler won
