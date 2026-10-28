"""Organization-aware collection with shared public data.

Three hypothetical organizations (a software company, a digital marketing
agency and a healthcare clinic) collect from the same public feeds. Identical
public requests are fetched once, while the searches, scores, alignment and
dashboards stay specific to each organization.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.models.trend import Trend
from app.services.alignment.service import ai_priority
from app.services.trends.industry import industry_terms, is_technology
from app.services.trends.inputs import load_org_inputs
from app.sources import default_sources
from app.workers import trend_tasks
from tests.conftest import register
from tests.test_trends_api import API, discover
from tests.trend_fixtures import FakeInternet, rfc822

# One public Google Trends feed, seen by all three organizations.
SHARED_TRENDS_RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>celebrity wedding</title><ht:approx_traffic>2M+</ht:approx_traffic>
<pubDate>{rfc822(1)}</pubDate></item>
<item><title>ai agents</title><ht:approx_traffic>500K+</ht:approx_traffic>
<pubDate>{rfc822(2)}</pubDate></item>
<item><title>google seo update</title><ht:approx_traffic>200K+</ht:approx_traffic>
<pubDate>{rfc822(2)}</pubDate></item>
<item><title>digital health app</title><ht:approx_traffic>100K+</ht:approx_traffic>
<pubDate>{rfc822(3)}</pubDate></item>
</channel></rss>"""

ORGS = {
    "software": {
        "name": "Byteworks",
        "industry": "Software & SaaS",
        "keywords": ["AI agents", "SaaS", "web development", "cloud computing"],
    },
    "agency": {
        "name": "Brightside Agency",
        "industry": "Digital marketing agency",
        "keywords": ["SEO", "social media", "advertising", "consumer behavior"],
    },
    # No keywords or services yet: collection starts from its industry.
    "clinic": {"name": "Riverside Clinic", "industry": "Healthcare clinic", "keywords": []},
}


@pytest.fixture
def shared_internet(monkeypatch):
    net = FakeInternet()
    urls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(request.url)
        if request.url.host == "trends.google.com":
            net.calls.append("trends.google.com" + request.url.path)
            return httpx.Response(200, text=SHARED_TRENDS_RSS)
        return net.handler(request)

    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(
        trend_tasks,
        "http_client_factory",
        lambda s: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(trend_tasks, "resolver", resolver)
    monkeypatch.setattr("app.sources.reddit.PUBLIC_DELAY_SECONDS", 0)
    net.urls = urls
    return net


async def three_orgs(client) -> dict:
    out = {}
    for key, spec in ORGS.items():
        admin = await register(client, f"admin@{key}.example.com")
        resp = await admin.post(
            "/api/v1/organizations",
            json={"name": spec["name"], "industry": spec["industry"], "timezone": "UTC"},
        )
        assert resp.status_code == 201, resp.text
        org = resp.json()
        resp = await admin.patch(
            f"/api/v1/organizations/{org['id']}/settings",
            json={"target_markets": ["USA"], "tracked_keywords": spec["keywords"]},
        )
        assert resp.status_code == 200, resp.text
        out[key] = (admin, org)
    return out


def test_industry_seeds():
    assert industry_terms("Healthcare clinic") == [
        "healthcare",
        "medical technology",
        "digital health",
    ]
    assert industry_terms("Digital marketing agency")[0] == "digital marketing"
    assert industry_terms("Software & SaaS")[0] == "software development"
    assert industry_terms("Artisan bakery") == ["Artisan bakery"]  # searched as written
    assert industry_terms(None) == [] and industry_terms("  ") == []
    # Whole words only: "skincare" is not "care", "said" is not "ai".
    assert industry_terms("Skincare brand") == ["Skincare brand"]
    assert is_technology("Cloud software") and not is_technology("Healthcare clinic")


def test_technology_sources_are_only_default_for_technology_organizations():
    assert "google_trends_tech" in default_sources("Software & SaaS")
    assert "google_trends_tech" not in default_sources("Healthcare clinic")
    assert "google_trends_tech" not in default_sources("Digital marketing agency")
    assert "google_trends_tech" not in default_sources(None)
    assert {"google_trends", "google_news", "hacker_news", "reddit", "rss"} <= set(
        default_sources(None)
    )


async def test_collection_inputs_follow_each_organization(client, db):
    orgs = await three_orgs(client)
    inputs = {k: await load_org_inputs(db, org["id"]) for k, (_, org) in orgs.items()}

    assert inputs["software"].inputs.keywords[:2] == ["AI agents", "SaaS"]
    assert inputs["software"].keyword_origin == "keywords"
    assert inputs["agency"].inputs.keywords[0] == "SEO"
    # The clinic searches healthcare, never a generic "technology" topic.
    assert inputs["clinic"].inputs.keywords == [
        "healthcare",
        "medical technology",
        "digital health",
    ]
    assert inputs["clinic"].keyword_origin == "industry"
    assert all("technology" != k.lower() for i in inputs.values() for k in i.inputs.keywords)
    assert {i.inputs.locations[0].code for i in inputs.values()} == {"US"}

    sources = {k: (await admin.get(f"{API}/sources")).json() for k, (admin, _) in orgs.items()}
    enabled = {k: {s["key"] for s in v if s["enabled"]} for k, v in sources.items()}
    assert "google_trends_tech" in enabled["software"]
    assert "google_trends_tech" not in enabled["clinic"]
    assert "google_trends_tech" not in enabled["agency"]


async def test_shared_public_items_are_scored_per_organization(client, shared_internet):
    orgs = await three_orgs(client)
    runs = {k: await discover(admin) for k, (admin, _) in orgs.items()}
    assert all(r["status"] == "succeeded" for r in runs.values()), runs
    assert any("searches used your industry" in w for w in runs["clinic"]["warnings"])

    # The public US Google Trends feed was fetched once for all three.
    assert shared_internet.calls.count("trends.google.com/trending/rss") == 1
    # Keyword searches are each organization's own.
    searched = {
        u.params.get("query")
        for u in shared_internet.urls
        if u.host == "hn.algolia.com" and u.params.get("query")
    }
    assert {"AI agents", "SEO", "healthcare"} <= searched
    assert "technology" not in searched

    def by_topic(admin):
        async def load():
            items = (await admin.get(API, params={"limit": 100})).json()["items"]
            return {t["topic"].lower(): t for t in items}

        return load()

    trends = {k: await by_topic(admin) for k, (admin, _) in orgs.items()}
    # Every organization stored its own copy of the same public items...
    for topic in ("ai agents", "google seo update", "digital health app", "celebrity wedding"):
        ids = {trends[k][topic]["id"] for k in trends}
        assert len(ids) == 3, topic
    # ...scored against its own profile.
    km = {
        k: {t: v["signals"]["keyword_match"]["score"] for t, v in m.items()}
        for k, m in trends.items()
    }
    assert km["software"]["ai agents"] == 100
    assert km["agency"]["google seo update"] == 100
    assert km["clinic"]["digital health app"] == 70  # industry match
    assert km["clinic"]["ai agents"] == 0
    assert km["software"]["digital health app"] < 70
    assert {km[k]["celebrity wedding"] for k in km} == {0}

    # Rule-based alignment (no LLM in tests) is per organization too.
    level = {k: {t: v["relevance_level"] for t, v in m.items()} for k, m in trends.items()}
    assert level["software"]["ai agents"] in ("relevant", "highly_relevant")
    assert level["clinic"]["ai agents"] == "not_relevant"
    # Industry adjacency alone isn't a tie to the clinic's own offering.
    assert level["clinic"]["digital health app"] == "weakly_relevant"
    assert level["agency"]["celebrity wedding"] == "not_relevant"

    # Dashboards only show each organization's own, relevant trends.
    for key, (admin, _) in orgs.items():
        top = (await admin.get("/api/v1/dashboard/summary")).json()["top_trends"]
        own_ids = {t["id"] for t in trends[key].values()}
        assert {t["id"] for t in top} <= own_ids
        topics = {t["topic"].lower() for t in top}
        assert "celebrity wedding" not in topics
    clinic_top = (await orgs["clinic"][0].get("/api/v1/dashboard/summary")).json()["top_trends"]
    assert "digital health app" in {t["topic"].lower() for t in clinic_top}
    assert "ai agents" not in {t["topic"].lower() for t in clinic_top}


async def test_ai_batch_prefers_fit_over_raw_popularity(client, db):
    _, org = (await three_orgs(client))["clinic"]
    now = datetime.now(UTC)

    def trend(topic, opportunity, keyword_score):
        return Trend(
            organization_id=org["id"],
            canonical_key=topic,
            topic=topic,
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now,
            opportunity_score=opportunity,
            signals={"keyword_match": {"score": keyword_score, "detail": ""}}
            if keyword_score is not None
            else {},
        )

    db.add_all(
        [
            trend("celebrity wedding", 82.0, 0),
            trend("digital health app", 55.0, 70),
            trend("hospital staffing", 48.0, 100),
            trend("unscored", None, None),
        ]
    )
    await db.commit()
    ordered = list(
        await db.scalars(
            select(Trend.topic)
            .where(Trend.organization_id == org["id"])
            .order_by(ai_priority().desc())
        )
    )
    assert ordered == ["hospital staffing", "digital health app", "celebrity wedding", "unscored"]
