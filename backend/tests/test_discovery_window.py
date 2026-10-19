"""One collection per discovery window: inside it, "Discover New Trends"
reads the stored trends and calls no provider."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.models.enums import DiscoveryRunStatus
from app.models.trend import TrendDiscoveryRun
from app.workers.runner import runner
from tests.conftest import create_org, register
from tests.test_trends_api import API, internet, setup  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def window_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "trend_manual_reuse_window", True)


async def _click(actor):
    resp = await actor.post(f"{API}/discover", json={})
    await runner.wait_idle()
    return resp


async def _run_count(db) -> int:
    return await db.scalar(select(func.count()).select_from(TrendDiscoveryRun))


async def test_second_click_inside_window_reads_stored_trends(client, internet, db):  # noqa: F811
    admin, _ = await setup(client)
    status = (await admin.get(f"{API}/discovery")).json()
    assert status["can_discover"] is True and status["next_discovery_at"] is None

    first = await _click(admin)
    assert first.status_code == 202 and first.json()["started"] is True
    calls = len(internet.calls)
    assert calls > 0
    trends_before = (await admin.get(API)).json()["total"]

    second = await _click(admin)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["started"] is False
    assert body["run_id"] == first.json()["run_id"]
    assert body["status"] == "succeeded"
    window = body["window"]
    assert window["background"] is True and window["can_discover"] is False
    assert window["new_trends"] == body["run"]["trends_created"] > 0
    run = await db.get(TrendDiscoveryRun, body["run_id"])
    assert window["next_discovery_at"] is not None
    next_at = datetime.fromisoformat(window["next_discovery_at"])
    assert next_at == run.created_at + timedelta(hours=3)

    # Nothing was collected: no provider request, no new run, same trends.
    assert len(internet.calls) == calls
    assert await _run_count(db) == 1
    assert (await admin.get(API)).json()["total"] == trends_before
    assert (await admin.get(f"{API}/discovery")).json() == window


async def test_discovery_collects_again_once_the_window_ends(client, internet, db):  # noqa: F811
    admin, _ = await setup(client)
    await _click(admin)
    await db.execute(
        update(TrendDiscoveryRun).values(
            created_at=TrendDiscoveryRun.created_at - timedelta(hours=3, minutes=1)
        )
    )
    await db.commit()
    assert (await admin.get(f"{API}/discovery")).json()["can_discover"] is True
    resp = await _click(admin)
    assert resp.status_code == 202 and resp.json()["started"] is True
    assert await _run_count(db) == 2


async def test_failed_discovery_never_blocks_the_button(client, internet, db):  # noqa: F811
    admin, _ = await setup(client)
    await _click(admin)
    await db.execute(update(TrendDiscoveryRun).values(status=DiscoveryRunStatus.FAILED))
    await db.commit()
    resp = await _click(admin)
    assert resp.status_code == 202 and resp.json()["started"] is True


async def test_without_background_discovery_the_manual_window_applies(
    client,
    internet,  # noqa: F811
    db,
    monkeypatch,
):
    monkeypatch.setattr(get_settings(), "trend_manual_window_minutes", 90)
    admin, org = await setup(client)
    resp = await admin.patch(
        f"/api/v1/organizations/{org['id']}/settings", json={"background_discovery": False}
    )
    assert resp.status_code == 200, resp.text
    first = await _click(admin)
    run = await db.get(TrendDiscoveryRun, first.json()["run_id"])
    window = (await _click(admin)).json()["window"]
    assert window["background"] is False and window["can_discover"] is False
    assert datetime.fromisoformat(window["next_discovery_at"]) == run.created_at + timedelta(
        minutes=90
    )


async def test_window_is_per_organization(client, internet, db):  # noqa: F811
    admin, _ = await setup(client)
    await _click(admin)
    other = await register(client, "owner@other.example.com")
    other_org = await create_org(other, name="Other Co")
    await other.patch(
        f"/api/v1/organizations/{other_org['id']}/settings",
        json={"target_markets": ["USA"], "tracked_keywords": ["GPT-6"]},
    )
    assert (await other.get(f"{API}/discovery")).json()["can_discover"] is True
    resp = await _click(other)
    assert resp.status_code == 202 and resp.json()["started"] is True


async def test_window_off_always_collects(client, internet, db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(get_settings(), "trend_manual_reuse_window", False)
    admin, _ = await setup(client)
    await _click(admin)
    resp = await _click(admin)
    assert resp.status_code == 202 and resp.json()["started"] is True
