"""POST /api/v1/internal/ingest/tick: the external (Supabase Cron) trigger."""

import asyncio

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.ratelimit import limiter
from app.models.trend import TrendDiscoveryRun
from app.workers import scheduler
from app.workers.runner import runner
from tests.test_trends_api import setup

URL = "/api/v1/internal/ingest/tick"
SECRET = "s" * 48


@pytest.fixture
def trigger(monkeypatch):
    monkeypatch.setattr(get_settings(), "ingest_trigger_secret", SECRET)
    monkeypatch.setattr(runner, "submit", lambda coro, name: coro.close())
    return {"X-Ingest-Secret": SECRET}


async def test_disabled_without_a_secret(client):
    assert (await client.post(URL)).status_code == 404


async def test_rejects_missing_and_wrong_secrets(client, trigger):
    assert (await client.post(URL)).status_code == 401
    resp = await client.post(URL, headers={"X-Ingest-Secret": "s" * 47 + "x"})
    assert resp.status_code == 401
    assert SECRET not in resp.text
    resp = await client.post(URL, headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401
    # Bearer works too.
    resp = await client.post(URL, headers={"Authorization": f"Bearer {SECRET}"})
    assert resp.status_code == 200


async def test_no_organizations_due(client, trigger):
    resp = await client.post(URL, headers=trigger)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "scheduled": 0, "recovered": 0}


async def test_schedules_only_due_organizations_and_tolerates_duplicates(client, trigger, db):
    admin, org = await setup(client)
    other_admin, other = await setup_manual(client)
    first = await client.post(URL, headers=trigger)
    assert first.json()["scheduled"] == 1  # the manual-only organization is never due
    # Duplicate and concurrent deliveries start nothing more.
    responses = await asyncio.gather(*(client.post(URL, headers=trigger) for _ in range(4)))
    assert all(r.status_code == 200 for r in responses)
    assert sum(r.json()["scheduled"] for r in responses) == 0
    runs = await db.scalar(select(func.count()).select_from(TrendDiscoveryRun))
    assert runs == 1


async def setup_manual(client):
    from tests.conftest import create_org, register

    admin = await register(client, "manual@b.example.com")
    org = await create_org(admin, "Manual Co")
    await admin.patch(
        f"/api/v1/organizations/{org['id']}/settings", json={"trend_frequency": "manual"}
    )
    return admin, org


async def test_database_failure_is_a_clean_503(client, trigger, monkeypatch):
    async def broken(now=None):
        raise OSError("database unreachable")

    monkeypatch.setattr(scheduler, "tick", broken)
    resp = await client.post(URL, headers=trigger)
    assert resp.status_code == 503
    assert "unreachable" not in resp.text  # no internals leaked


async def test_oversized_bodies_and_hammering_are_refused(client, trigger, monkeypatch):
    resp = await client.post(URL, headers=trigger, content=b"x" * 5000)
    assert resp.status_code == 413
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    try:
        codes = [(await client.post(URL, headers=trigger)).status_code for _ in range(8)]
    finally:
        limiter.reset()
    assert codes[:6] == [200] * 6 and codes[6:] == [429, 429]


def test_short_secrets_are_rejected_at_startup():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, ingest_trigger_secret="too-short")
