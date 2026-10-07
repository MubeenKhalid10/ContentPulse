from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.enums import TrendFrequency
from app.models.trend import TrendDiscoveryRun, TrendSource
from app.services.trends.clustering import cluster_items, similar_keys
from app.services.trends.scoring import MentionView, OrgProfile, score_trend
from app.services.trends.text import candidate_phrases, canonical_key
from app.sources.base import RawTrendItem
from app.workers import scheduler, trend_tasks
from app.workers.runner import runner
from tests.conftest import add_member, create_org, register
from tests.trend_fixtures import FakeInternet

API = "/api/v1/trends"

# --- Text, clustering and scoring -------------------------------------------------------


def test_canonical_keys_are_order_and_plural_insensitive():
    assert canonical_key("Interest Rates") == canonical_key("rate interest")
    assert canonical_key("OpenAI's GPT-6") == canonical_key("gpt-6 openai")


def test_candidate_phrases():
    assert "Federal Reserve" in candidate_phrases("Federal Reserve holds rates steady")
    assert "Russia" in candidate_phrases("How Russia is reshaping energy markets")
    assert "GPT-6" in candidate_phrases("Why the new GPT-6 matters")
    # Title Case headlines: capitals are not evidence, acronyms/digits still are.
    phrases = candidate_phrases("Software Is Eating The World Again With GPT-6")
    assert "GPT-6" in phrases and not any("Software" in p for p in phrases)


def test_similar_keys():
    assert similar_keys("gpt-6 openai", "gpt-6 openai launch")
    assert not similar_keys("ai", "ai startup funding")  # 'ai' too broad to absorb
    assert not similar_keys("naomi osaka", "gpt-6 openai")


def item(source, title, *, topic=None, engagement=None, sid=None):
    return RawTrendItem(
        source=source,
        source_item_id=sid or title,
        title=title,
        topic=topic,
        engagement=engagement,
        published_at=datetime.now(UTC) - timedelta(hours=2),
    )


def test_clustering_groups_across_sources_and_drops_noise():
    clusters, unclustered = cluster_items(
        [
            item("google_trends", "openai gpt-6", topic="openai gpt-6", engagement=200_000),
            item("google_news", "OpenAI GPT-6 arrives with agents"),
            item("google_news", "What GPT-6 means for finance teams"),
            item("hacker_news", "GPT-6 benchmarks are in", engagement=450),
            item("google_news", "Local bakery wins regional award"),
        ],
        tracked_keywords=["automation"],
    )
    biggest = max(clusters, key=lambda c: len(c.items))
    assert {i.source for i in biggest.items} == {"google_trends", "google_news", "hacker_news"}
    assert unclustered == 1  # the bakery story


def test_tracked_keywords_never_become_a_bucket_topic():
    clusters, _ = cluster_items(
        [item("google_news", f"Story {n} about automation in logistics") for n in range(5)],
        tracked_keywords=["automation"],
    )
    assert all(c.key != "automation" for c in clusters)


def test_news_api_keyword_match_can_stand_alone():
    clusters, unclustered = cluster_items(
        [item("world_news", "New software development tools help small teams")],
        tracked_keywords=["Software Development"],
    )
    assert unclustered == 0
    assert len(clusters) == 1
    assert clusters[0].key == canonical_key("Software Development")


def test_scores_are_explained():
    now = datetime.now(UTC)
    mentions = [
        MentionView(
            "google_trends", "openai gpt-6", 200_000, now - timedelta(hours=1), now, "US", None
        ),
        MentionView(
            "hacker_news", "GPT-6 benchmarks", 450, now - timedelta(hours=5), now, "GLOBAL", 30.0
        ),
        MentionView(
            "google_news", "GPT-6 arrives", None, now - timedelta(hours=2), now, "GB", None
        ),
    ]
    profile = OrgProfile(markets={"US"}, tracked_keywords=["GPT-6"], service_names=["AI Solutions"])
    signals, score = score_trend(
        mentions, topic="OpenAI GPT-6", keywords=[], profile=profile, now=now
    )
    assert set(signals) == {
        "popularity",
        "growth",
        "freshness",
        "location_relevance",
        "source_diversity",
        "keyword_match",
    }
    assert signals["location_relevance"] == {"score": 100, "detail": "Trending in United States"}
    assert signals["keyword_match"]["detail"] == "Matches tracked keyword “GPT-6”"
    assert signals["source_diversity"]["score"] == 80
    assert "200K searches on Google Trends" in signals["popularity"]["detail"]
    assert 60 < score <= 100


@pytest.mark.parametrize(
    ("frequency", "hours_since_last", "expected"),
    [
        (TrendFrequency.MANUAL, None, False),
        (TrendFrequency.HOURLY, None, True),
        (TrendFrequency.HOURLY, 0.5, False),
        (TrendFrequency.HOURLY, 1.1, True),
        (TrendFrequency.EVERY_6_HOURS, 5, False),
        (TrendFrequency.EVERY_6_HOURS, 6.5, True),
    ],
)
def test_interval_schedules(frequency, hours_since_last, expected):
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    last = now - timedelta(hours=hours_since_last) if hours_since_last is not None else None
    assert scheduler.is_due(frequency, last, now, "UTC") is expected


def test_daily_schedule_runs_after_8am_local():
    # 07:30 in London (BST = UTC+1) is 06:30 UTC.
    before_8 = datetime(2026, 7, 1, 6, 30, tzinfo=UTC)
    yesterday_9am = datetime(2026, 6, 30, 8, 0, tzinfo=UTC)
    assert not scheduler.is_due(TrendFrequency.DAILY, yesterday_9am, before_8, "Europe/London")
    after_8 = datetime(2026, 7, 1, 7, 5, tzinfo=UTC)  # 08:05 local
    assert scheduler.is_due(TrendFrequency.DAILY, yesterday_9am, after_8, "Europe/London")
    assert not scheduler.is_due(
        TrendFrequency.DAILY, after_8, after_8 + timedelta(hours=3), "Europe/London"
    )


# --- API ------------------------------------------------------------------------------------


@pytest.fixture
def internet(monkeypatch):
    net = FakeInternet()
    net.fail("www.reddit.com", 429)  # Reddit is rate limiting us today

    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(
        trend_tasks,
        "http_client_factory",
        lambda s: httpx.AsyncClient(transport=httpx.MockTransport(net.handler)),
    )
    monkeypatch.setattr(trend_tasks, "resolver", resolver)
    monkeypatch.setattr("app.sources.reddit.PUBLIC_DELAY_SECONDS", 0)
    return net


async def setup(client, markets=("USA",)):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    await admin.patch(
        f"/api/v1/organizations/{org['id']}/settings",
        json={"target_markets": list(markets), "tracked_keywords": ["GPT-6"]},
    )
    return admin, org


async def discover(actor, **body) -> dict:
    resp = await actor.post(f"{API}/discover", json=body)
    assert resp.status_code == 202, resp.text
    await runner.wait_idle()
    return (await actor.get(f"{API}/runs/{resp.json()['run_id']}")).json()


async def test_sources_listing_without_any_keys(client):
    admin, _ = await setup(client)
    sources = {s["key"]: s for s in (await admin.get(f"{API}/sources")).json()}
    assert len(sources) == 14
    assert sources["google_trends"]["configured"] and sources["google_trends"]["enabled"]
    assert sources["newsapi"]["configured"] is False
    assert sources["newsapi"]["missing"] == ["NEWS_API_KEY"]
    assert sources["newsapi"]["enabled"] is False
    assert sources["rss"]["enabled"] is True and sources["rss"]["configured"] is False
    assert sources["linkedin"]["pricing"] == "unavailable"


async def test_discovery_survives_failing_and_unconfigured_sources(client, internet, db):
    admin, org = await setup(client)
    run = await discover(admin)

    assert run["status"] == "succeeded", run
    results = run["results"]
    assert results["google_trends"]["status"] == "ok"
    assert results["google_news"]["status"] == "ok"
    assert results["hacker_news"]["status"] == "ok"
    assert results["reddit"]["status"] == "failed"
    assert results["reddit"]["error_kind"] == "rate_limited"
    assert results["rss"]["status"] == "not_configured"
    assert run["trends_created"] >= 2 and run["mentions_created"] >= 4

    health = {s.key: s for s in await db.scalars(select(TrendSource))}
    assert health["reddit"].health == "rate_limited"
    assert health["google_trends"].health == "healthy"

    trends = (await admin.get(API)).json()
    top = trends["items"][0]
    assert "gpt-6" in top["topic"].lower()
    assert set(top["sources"]) >= {"google_trends", "google_news", "hacker_news"}
    assert top["signals"]["keyword_match"]["score"] == 100
    assert top["signals"]["location_relevance"]["detail"] == "Trending in United States"

    detail = (await admin.get(f"{API}/{top['id']}")).json()
    assert detail["mentions"][0]["engagement"] == 200_000  # sorted by engagement
    assert any(m["source"] == "hacker_news" for m in detail["mentions"])

    summary = (await admin.get("/api/v1/dashboard/summary")).json()
    assert summary["trends_today"] >= 2
    assert summary["top_trends"][0]["id"] == top["id"]


async def test_rediscovery_deduplicates_and_tracks_growth(client, internet):
    admin, _ = await setup(client)
    await discover(admin)
    first = (await admin.get(API)).json()

    run = await discover(admin)
    assert run["trends_created"] == 0 and run["mentions_created"] == 0
    second = (await admin.get(API)).json()
    assert second["total"] == first["total"]
    assert second["items"][0]["mention_count"] == first["items"][0]["mention_count"]


async def test_discovery_with_all_sources_down_fails_cleanly(client, internet):
    for host in ("trends.google.com", "news.google.com", "hn.algolia.com"):
        internet.fail(host, 503)
    admin, _ = await setup(client)
    run = await discover(admin)
    assert run["status"] == "failed"
    assert run["error"].startswith("All sources failed.")
    assert (await admin.get(API)).json()["total"] == 0


async def test_discover_only_unconfigured_sources(client, internet):
    admin, _ = await setup(client)
    run = await discover(admin, sources=["newsapi", "x"])
    assert run["status"] == "failed"
    assert "None of the enabled sources are configured" in run["error"]
    assert run["results"]["newsapi"] == {
        "status": "not_configured",
        "items": 0,
        "error": "Set NEWS_API_KEY.",
        "error_kind": None,
        "mode": None,
        "duration_ms": None,
    }


async def test_configured_key_activates_source(client, internet, monkeypatch):
    monkeypatch.setattr(get_settings(), "news_api_key", "test-key")
    admin, _ = await setup(client)
    resp = await admin.patch(f"{API}/sources/newsapi", json={"enabled": True})
    newsapi = next(s for s in resp.json() if s["key"] == "newsapi")
    assert newsapi["configured"] and newsapi["enabled"]
    run = await discover(admin, sources=["newsapi"])
    assert run["status"] == "succeeded" and run["results"]["newsapi"]["items"] >= 1


async def test_validation_and_conflicts(client, internet, monkeypatch):
    admin, org = await setup(client)
    resp = await admin.post(f"{API}/discover", json={"sources": ["myspace"]})
    assert resp.status_code == 422 and "Unknown source" in resp.json()["error"]["message"]

    resp = await admin.patch(
        f"/api/v1/organizations/{org['id']}/settings", json={"enabled_sources": ["myspace"]}
    )
    assert resp.status_code == 422
    resp = await admin.patch(
        f"/api/v1/organizations/{org['id']}/settings",
        json={"subreddits": ["r/automation", "not a subreddit!"]},
    )
    assert resp.status_code == 422

    monkeypatch.setattr(runner, "submit", lambda coro, name: coro.close())
    assert (await admin.post(f"{API}/discover", json={})).status_code == 202
    resp = await admin.post(f"{API}/discover", json={})
    assert resp.status_code == 409 and "run_id" in resp.json()["error"]["details"]


async def test_disabled_sources_mean_no_discovery(client):
    admin, org = await setup(client)
    await admin.patch(f"/api/v1/organizations/{org['id']}/settings", json={"enabled_sources": []})
    resp = await admin.post(f"{API}/discover", json={})
    assert (
        resp.status_code == 422
        and "No trend sources are enabled" in resp.json()["error"]["message"]
    )


async def test_review_workflow_and_permissions(client, internet):
    admin, org = await setup(client)
    await discover(admin)
    manager = await add_member(client, admin, org["id"], "cm@acme.example.com", "creator")
    viewer = await add_member(client, admin, org["id"], "viewer@acme.example.com", "viewer")
    trend = (await admin.get(API)).json()["items"][0]

    # Viewers read; content managers review (shortlist/reject) but can't run discovery.
    assert (await viewer.get(API)).status_code == 200
    assert (await viewer.post(f"{API}/{trend['id']}/shortlist")).status_code == 403
    assert (await manager.post(f"{API}/discover", json={})).status_code == 403
    resp = await manager.post(f"{API}/{trend['id']}/shortlist")
    assert resp.status_code == 200 and resp.json()["status"] == "shortlisted"

    shortlisted = (await admin.get(API, params={"status": "shortlisted"})).json()
    assert [t["id"] for t in shortlisted["items"]] == [trend["id"]]

    assert (await manager.post(f"{API}/{trend['id']}/reject")).json()["status"] == "rejected"
    # Discovery already analyzed it (rule-based without an LLM), so it returns to "analyzed".
    assert (await manager.post(f"{API}/{trend['id']}/restore")).json()["status"] == "analyzed"
    resp = await manager.post(f"{API}/{trend['id']}/restore")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    actions = [
        e["action"]
        for e in (await admin.get(f"/api/v1/organizations/{org['id']}/audit-logs")).json()
    ]
    assert {"TREND_SHORTLISTED", "TREND_REJECTED", "TREND_RESTORED"} <= set(actions)


async def test_trend_isolation(client, internet):
    admin, _ = await setup(client)
    await discover(admin)
    trend_id = (await admin.get(API)).json()["items"][0]["id"]
    outsider = await register(client, "out@other.example.com")
    await create_org(outsider, "Other")
    assert (await outsider.get(API)).json()["total"] == 0
    assert (await outsider.get(f"{API}/{trend_id}")).status_code == 404
    assert (await outsider.post(f"{API}/{trend_id}/reject")).status_code == 404


async def test_scheduler_creates_due_runs_once(client, internet, db, monkeypatch):
    submitted = []
    monkeypatch.setattr(runner, "submit", lambda coro, name: submitted.append(coro))
    await setup(client)  # new orgs default to daily collection
    assert await scheduler.schedule_due_runs() == 1
    assert await scheduler.schedule_due_runs() == 0  # one is already queued
    run = await db.scalar(select(TrendDiscoveryRun))
    assert run.trigger == "scheduled" and "google_trends" in run.sources
    for coro in submitted:
        await coro
    await db.refresh(run)
    assert run.status == "succeeded"


async def test_concurrent_organizations_share_provider_requests(client, internet):
    admin, _ = await setup(client)
    other = await register(client, "other@b.example.com")
    org_b = await create_org(other, "Other Co")
    await other.patch(
        f"/api/v1/organizations/{org_b['id']}/settings",
        json={"target_markets": ["USA"], "tracked_keywords": ["GPT-6"]},
    )
    await discover(admin)
    calls_after_first = len(internet.calls)
    run = await discover(other)
    assert run["status"] == "succeeded" and run["trends_created"] >= 2
    # Same markets and keywords: every provider response came from the shared cache.
    assert len(internet.calls) == calls_after_first


def test_related_keywords_need_to_recur():
    from app.services.trends.text import top_terms

    titles = [
        "Senator introduces bill on AI workers",
        "AI adds new risks for banks",
        "Banks race to adopt AI agents",
    ]
    terms = top_terms(titles)
    assert "bank" in terms
    assert "add" not in terms and "senator" not in terms  # appear once
