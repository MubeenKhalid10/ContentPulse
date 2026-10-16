"""Organization B must never see Organization A's private trend inputs or results.

Covers the platform-wide source health leak (an RSS error carried A's feed URL
into `trend_sources.last_error`, which every organization's Sources page showed)
and the per-organization APIs around discovery.
"""

import json
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.models.trend import TrendSource
from tests.conftest import create_org, register
from tests.test_trends_api import API, discover, internet  # noqa: F401  (fixture)

SECRET_FEED = "https://private-feed.example.org/members/rss?token=s3cr3t-A-token"


async def two_orgs(client):
    admin_a = await register(client, "a@alpha.example.com")
    org_a = await create_org(admin_a, "Alpha")
    resp = await admin_a.patch(
        f"/api/v1/organizations/{org_a['id']}/settings",
        json={
            "target_markets": ["USA"],
            "tracked_keywords": ["GPT-6", "alpha-secret-keyword"],
            "rss_feeds": [SECRET_FEED],
        },
    )
    assert resp.status_code == 200, resp.text
    admin_b = await register(client, "b@beta.example.com")
    org_b = await create_org(admin_b, "Beta")
    return admin_a, org_a, admin_b, org_b


async def test_rss_failure_stays_inside_its_organization(client, internet, db):  # noqa: F811
    internet.fail("private-feed.example.org", 500)
    admin_a, org_a, admin_b, _ = await two_orgs(client)
    run = await discover(admin_a)
    assert run["results"]["rss"]["status"] == "failed"
    # A still sees its own diagnostics, URL included.
    assert "private-feed.example.org" in run["results"]["rss"]["error"]
    a_rss = next(s for s in (await admin_a.get(f"{API}/sources")).json() if s["key"] == "rss")
    assert a_rss["health"] == "degraded" and "private-feed.example.org" in a_rss["last_error"]

    # Nothing about A's feed is recorded platform-wide...
    row = await db.scalar(select(TrendSource).where(TrendSource.key == "rss"))
    assert row is None or (row.last_error is None and row.last_failure_at is None)
    # ...and B's Sources page shows nothing of it.
    resp = await admin_b.get(f"{API}/sources")
    body = resp.text
    assert "private-feed" not in body and "s3cr3t" not in body
    b_rss = next(s for s in resp.json() if s["key"] == "rss")
    assert b_rss["health"] == "unknown" and b_rss["last_error"] is None
    assert b_rss["last_failure_at"] is None


async def test_provider_error_bodies_are_not_stored_platform_wide(
    client,
    internet,  # noqa: F811
    db,
    monkeypatch,
):
    # A provider that echoes the (organization-specific) query in its error body.
    monkeypatch.setattr(get_settings(), "news_api_key", "test-key")
    internet.fail("newsapi.org", 400, json.dumps({"message": "bad query alpha-secret-keyword"}))
    admin_a, _, admin_b, _ = await two_orgs(client)
    run = await discover(admin_a, sources=["newsapi"])
    assert "alpha-secret-keyword" in run["results"]["newsapi"]["error"]  # A's own run

    row = await db.scalar(select(TrendSource).where(TrendSource.key == "newsapi"))
    assert row.last_error == (
        "The provider rejected a request or sent an unexpected response. (HTTP 400)"
    )
    assert "alpha-secret-keyword" not in (await admin_b.get(f"{API}/sources")).text


async def test_legacy_leaked_health_text_is_hidden(client, db):
    """Rows written before sanitizing may hold another organization's details."""
    for key in ("rss", "newsapi"):
        db.add(
            TrendSource(
                id=uuid.uuid4(),
                key=key,
                name=key,
                health="degraded",
                last_error=f"{SECRET_FEED}: HTTP 500",
            )
        )
    await db.commit()
    admin_b = await register(client, "b@beta.example.com")
    await create_org(admin_b, "Beta")
    resp = await admin_b.get(f"{API}/sources")
    assert "s3cr3t" not in resp.text and "private-feed" not in resp.text
    sources = {s["key"]: s for s in resp.json()}
    assert sources["newsapi"]["last_error"] == "The last request failed."
    assert sources["newsapi"]["health"] == "degraded"
    assert sources["rss"]["health"] == "unknown"  # B has never run its own feeds


async def test_other_organization_cannot_reach_private_data(client, internet):  # noqa: F811
    admin_a, org_a, admin_b, org_b = await two_orgs(client)
    run = await discover(admin_a)
    trend = (await admin_a.get(API)).json()["items"][0]

    # Settings (feeds, keywords), runs, trends and mentions are all A's alone.
    for url in (
        f"/api/v1/organizations/{org_a['id']}/settings",
        f"/api/v1/organizations/{org_a['id']}",
        f"{API}/runs/{run['id']}",
        f"{API}/{trend['id']}",
    ):
        assert (await admin_b.get(url)).status_code == 404, url
    # Asking for A explicitly through the organization header doesn't help.
    resp = await admin_b.get(API, headers={"X-Organization-Id": org_a["id"]})
    assert resp.status_code == 404

    assert (await admin_b.get(f"{API}/runs")).json() == []
    assert (await admin_b.get(API)).json()["total"] == 0
    summary = (await admin_b.get("/api/v1/dashboard/summary")).text
    assert trend["id"] not in summary
    b_settings = (await admin_b.get(f"/api/v1/organizations/{org_b['id']}/settings")).text
    assert "alpha-secret-keyword" not in b_settings and "private-feed" not in b_settings


async def test_other_organization_cannot_change_or_delete_private_data(client, internet):  # noqa: F811
    admin_a, org_a, admin_b, _ = await two_orgs(client)
    await discover(admin_a)
    trend = (await admin_a.get(API)).json()["items"][0]
    org_url = f"/api/v1/organizations/{org_a['id']}"
    as_a = {"X-Organization-Id": org_a["id"]}

    attempts = [
        ("PATCH", org_url, {"name": "Taken over"}),
        ("DELETE", org_url, None),
        ("PATCH", f"{org_url}/settings", {"rss_feeds": ["https://evil.example.com/rss"]}),
        ("PATCH", f"{org_url}/brand", {"tone_of_voice": "hijacked"}),
        ("POST", f"{org_url}/services", {"name": "Injected"}),
        ("POST", f"{org_url}/invitations", {"email": "mallory@b.example.com", "role": "admin"}),
        ("POST", f"{org_url}/knowledge/documents", {"title": "x", "content": "x"}),
        ("POST", f"{API}/{trend['id']}/shortlist", {}),
        ("DELETE", f"{API}/{trend['id']}", None),
    ]
    for method, url, body in attempts:
        for headers in ({}, as_a):
            resp = await admin_b.request(method, url, json=body, headers=headers)
            assert resp.status_code == 404, (method, url, headers, resp.status_code)

    # A's data is exactly as it was.
    assert (await admin_a.get(org_url)).json()["name"] == "Alpha"
    settings = (await admin_a.get(f"{org_url}/settings")).json()
    assert settings["rss_feeds"] == [SECRET_FEED]
    assert (await admin_a.get(f"{API}/{trend['id']}")).json()["status"] == trend["status"]
    members = (await admin_a.get(f"{org_url}/members")).json()
    assert len(members) == 1
