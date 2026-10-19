"""Discovery Sources: per-organization source preferences filter the feed.

Attribution comes from trend_mentions.source; filtering happens in the API
and never contacts a provider.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.audit import AuditLog
from app.models.enums import TrendStatus
from app.models.trend import Trend, TrendDiscoveryRun, TrendMention
from app.workers import trend_tasks
from tests.conftest import add_member, create_org, register

API = "/api/v1/trends"
DASHBOARD = "/api/v1/dashboard"


@pytest.fixture(autouse=True)
def no_provider_calls(monkeypatch):
    """Any provider request during these tests is a bug."""

    def refuse(_settings):
        raise AssertionError("source filtering must not call providers")

    monkeypatch.setattr(trend_tasks, "http_client_factory", refuse)


async def seed_trend(db, org_id: str, topic: str, sources: list[str], score: float = 50):
    now = datetime.now(UTC)
    trend = Trend(
        organization_id=uuid.UUID(org_id),
        canonical_key=topic.lower(),
        topic=topic,
        first_seen_at=now - timedelta(hours=1),
        last_seen_at=now,
        status=TrendStatus.NEW,
        opportunity_score=score,
        # Deliberately stale denormalized list: filtering must use mentions.
        sources=["google_trends"],
        mention_count=len(sources),
    )
    db.add(trend)
    await db.flush()
    for i, source in enumerate(sources):
        db.add(
            TrendMention(
                organization_id=trend.organization_id,
                trend_id=trend.id,
                source=source,
                source_item_id=f"{topic}-{i}",
                topic=topic,
                title=topic,
                detected_at=now,
            )
        )
    await db.commit()
    return str(trend.id)


async def seed_feed(db, org_id: str) -> dict[str, str]:
    return {
        "news_only": await seed_trend(db, org_id, "News only", ["google_news"], 90),
        "reddit_only": await seed_trend(db, org_id, "Reddit only", ["reddit", "reddit"], 80),
        "reddit_hn": await seed_trend(db, org_id, "Reddit and HN", ["reddit", "hacker_news"], 70),
        "no_mentions": await seed_trend(db, org_id, "Unattributed", [], 60),
        "legacy_key": await seed_trend(db, org_id, "Legacy source", ["news"], 55),
    }


async def setup(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    return admin, org


async def feed(actor, **params) -> set[str]:
    resp = await actor.get(API, params={"status": "all", **params})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == len(body["items"])
    return {t["id"] for t in body["items"]}


async def toggle(actor, key: str, enabled: bool):
    return await actor.patch(f"{API}/sources/{key}", json={"enabled": enabled})


async def test_preferences_persist_and_are_audited(client, db):
    admin, org = await setup(client)
    resp = await toggle(admin, "reddit", False)
    assert resp.status_code == 200
    assert {s["key"]: s["enabled"] for s in resp.json()}["reddit"] is False

    # Persisted in organization_settings.enabled_sources (no new table).
    sources = {s["key"]: s for s in (await admin.get(f"{API}/sources")).json()}
    assert sources["reddit"]["enabled"] is False and sources["google_news"]["enabled"] is True
    org_settings = (await admin.get(f"/api/v1/organizations/{org['id']}/settings")).json()
    assert "reddit" not in org_settings["enabled_sources"]
    assert "google_news" in org_settings["enabled_sources"]

    assert (await toggle(admin, "reddit", True)).status_code == 200
    org_settings = (await admin.get(f"/api/v1/organizations/{org['id']}/settings")).json()
    assert "reddit" in org_settings["enabled_sources"]

    audits = await db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.entity_type == "organization_settings")
    )
    assert audits == 2
    # Toggling never starts collection.
    assert await db.scalar(select(func.count()).select_from(TrendDiscoveryRun)) == 0


async def test_feed_filtering_by_enabled_sources(client, db):
    admin, org = await setup(client)
    ids = await seed_feed(db, org["id"])

    # Defaults include google_news, reddit and hacker_news. Unattributed
    # trends and unknown (legacy) source keys are never shown.
    assert await feed(admin) == {ids["news_only"], ids["reddit_only"], ids["reddit_hn"]}

    # Multi-source trend stays while one of its sources is still enabled.
    await toggle(admin, "reddit", False)
    assert await feed(admin) == {ids["news_only"], ids["reddit_hn"]}

    # ...and disappears once all of its sources are off.
    await toggle(admin, "hacker_news", False)
    assert await feed(admin) == {ids["news_only"]}

    # Re-enabling brings it back: nothing was deleted.
    await toggle(admin, "reddit", True)
    assert await feed(admin) == {ids["news_only"], ids["reddit_only"], ids["reddit_hn"]}


async def test_source_query_param_respects_preferences(client, db):
    admin, org = await setup(client)
    ids = await seed_feed(db, org["id"])
    # Mention attribution, not the stale Trend.sources column.
    assert await feed(admin, source="reddit") == {ids["reddit_only"], ids["reddit_hn"]}
    assert await feed(admin, source="google_trends") == set()
    await toggle(admin, "reddit", False)
    assert await feed(admin, source="reddit") == set()


async def test_status_tabs_are_filtered_too(client, db):
    admin, org = await setup(client)
    ids = await seed_feed(db, org["id"])
    await admin.post(f"{API}/{ids['reddit_only']}/shortlist")
    assert await feed(admin, status="shortlisted") == {ids["reddit_only"]}
    await toggle(admin, "reddit", False)
    assert await feed(admin, status="shortlisted") == set()
    # The trend itself is untouched and still reachable directly (topics link to it).
    resp = await admin.get(f"{API}/{ids['reddit_only']}")
    assert resp.status_code == 200 and resp.json()["status"] == "shortlisted"


async def test_no_enabled_sources_means_empty_feed(client, db):
    admin, org = await setup(client)
    await seed_feed(db, org["id"])
    resp = await admin.patch(
        f"/api/v1/organizations/{org['id']}/settings", json={"enabled_sources": []}
    )
    assert resp.status_code == 200
    assert await feed(admin) == set()


async def test_dashboard_respects_preferences(client, db):
    admin, org = await setup(client)
    ids = await seed_feed(db, org["id"])
    # The label comes from the denormalized list; it must skip disabled sources.
    news = await db.get(Trend, uuid.UUID(ids["news_only"]))
    news.sources = ["reddit", "google_news"]
    await db.commit()
    await toggle(admin, "reddit", False)
    await toggle(admin, "hacker_news", False)

    summary = (await admin.get(f"{DASHBOARD}/summary")).json()
    assert [t["id"] for t in summary["top_trends"]] == [ids["news_only"]]
    assert summary["trends_today"] == 1

    overview = (await admin.get(f"{DASHBOARD}/overview")).json()
    assert [t["id"] for t in overview["trending"]] == [ids["news_only"]]
    assert overview["trending"][0]["source"] == "google_news"


async def test_preferences_are_isolated_between_organizations(client, db):
    admin, org = await setup(client)
    ids = await seed_feed(db, org["id"])
    other = await register(client, "admin@other.example.com")
    other_org = await create_org(other, "Other Co")
    other_ids = await seed_feed(db, other_org["id"])

    await toggle(other, "reddit", False)
    await toggle(other, "hacker_news", False)
    assert await feed(other) == {other_ids["news_only"]}
    # The first organization still sees its Reddit and HN trends.
    assert await feed(admin) == {ids["news_only"], ids["reddit_only"], ids["reddit_hn"]}
    sources = {s["key"]: s["enabled"] for s in (await admin.get(f"{API}/sources")).json()}
    assert sources["reddit"] and sources["hacker_news"]

    # An outsider can't read or change another organization's preferences.
    foreign = {"X-Organization-Id": org["id"]}
    assert (await other.get(f"{API}/sources", headers=foreign)).status_code in (403, 404)
    resp = await other.patch(f"{API}/sources/google_news", json={"enabled": False}, headers=foreign)
    assert resp.status_code in (403, 404)
    resp = await other.patch(
        f"/api/v1/organizations/{org['id']}/settings", json={"enabled_sources": []}
    )
    assert resp.status_code in (403, 404)
    assert ids["news_only"] in await feed(admin)


async def test_unauthorized_and_invalid_changes(client, db):
    admin, org = await setup(client)
    viewer = await add_member(client, admin, org["id"], "viewer@acme.example.com", "viewer")
    creator = await add_member(client, admin, org["id"], "cm@acme.example.com", "creator")

    assert (await viewer.get(f"{API}/sources")).status_code == 200
    assert (await toggle(viewer, "reddit", False)).status_code == 403
    assert (await toggle(creator, "reddit", False)).status_code == 403
    resp = await client.patch(f"{API}/sources/reddit", json={"enabled": False})
    assert resp.status_code == 401

    # Unknown identifiers are rejected by both write paths.
    assert (await toggle(admin, "myspace", True)).status_code == 404
    resp = await admin.patch(
        f"/api/v1/organizations/{org['id']}/settings", json={"enabled_sources": ["myspace"]}
    )
    assert resp.status_code == 422
    resp = await admin.patch(f"{API}/sources/reddit", json={"enabled": "maybe"})
    assert resp.status_code == 422

    sources = {s["key"]: s["enabled"] for s in (await admin.get(f"{API}/sources")).json()}
    assert sources["reddit"] is True
