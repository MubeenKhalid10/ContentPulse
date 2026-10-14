"""Shared provider-response cache: safe keys, persistence, leases, retention."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, text, update

from app.core.config import Settings, get_settings
from app.models.provider import ProviderCache
from app.sources import SOURCES, provider_cache
from app.sources.base import (
    SourceContext,
    SourceError,
    SourceErrorKind,
    SourceInputs,
    request_cache,
)
from app.sources.cache_policy import POLICIES, canonical_request
from app.sources.locations import resolve_markets
from app.sources.provider_cache import cache_stats, prepare, store
from tests.trend_fixtures import FakeInternet

SINCE = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)


def key(name, params=None, *, url="https://api.example/x", method="GET", body=None):
    prepared = prepare(name, method, url, params, body)
    return prepared.key if prepared else None


@pytest.fixture
def postgres_cache(monkeypatch):
    """Persist the given sources in Postgres (the default is memory only)."""
    settings = get_settings()

    def enable(*sources: str):
        monkeypatch.setattr(settings, "provider_cache_backend", "postgres")
        monkeypatch.setattr(settings, "provider_cache_persist_sources", list(sources))

    monkeypatch.setattr(settings, "provider_cache_wait_seconds", 2.0)
    return enable


async def run_source(
    source, *, settings=None, keywords=("automation",), markets=("USA",), net=None
):
    net = net or FakeInternet()
    locations, _ = resolve_markets(list(markets))
    async with httpx.AsyncClient(transport=httpx.MockTransport(net.handler)) as client:
        ctx = SourceContext(
            client=client,
            settings=settings or Settings(_env_file=None),
            inputs=SourceInputs(locations=locations, keywords=list(keywords)),
            since=SINCE - timedelta(hours=48),
        )
        items = await SOURCES[source].collect(ctx)
    return items, net


# --- Key normalization ---------------------------------------------------------------


def test_secrets_never_change_or_enter_the_key():
    a = key("newsdata", {"apikey": "secret-A", "q": "cloud", "language": "en"})
    b = key("newsdata", {"apikey": "secret-B", "q": "cloud", "language": "en"})
    assert a == b and a is not None
    parts = canonical_request(
        "newsdata",
        POLICIES["newsdata"],
        "GET",
        "https://newsdata.io/api/1/latest?apikey=secret-A",
        {"q": "cloud"},
    )
    assert "secret" not in json.dumps(parts.__dict__)
    # Credentials carried in any of the usual parameter names are dropped too.
    assert key("google_trends", {"geo": "US", "api_key": "x"}) == key(
        "google_trends", {"geo": "US"}
    )


def test_order_case_whitespace_and_sets_are_normalized():
    base = {"q": "cloud  computing OR SaaS", "language": "en", "country": "us,gb"}
    same = {"country": "GB, US", "language": "en", "q": "cloud computing OR SaaS"}
    assert key("newsdata", base) == key("newsdata", same)
    # Packed queries keep their case: "a OR b" (operator) is not "a or b" (words).
    assert key("newsdata", {"q": "a OR b"}) != key("newsdata", {"q": "a or b"})
    assert key("hacker_news", {"query": "SaaS", "tags": "story"}) == key(
        "hacker_news", {"tags": "story", "query": "saas"}
    )


def test_results_affecting_differences_are_kept():
    us = key("google_trends", {"geo": "US"})
    assert us != key("google_trends", {"geo": "GB"})
    news = {"q": "cloud", "language": "en"}
    assert key("newsdata", news) != key("newsdata", {**news, "q": "seo"})
    assert key("newsdata", news) != key("newsdata", {**news, "language": "de"})
    assert key("newsdata", news) != key("newsdata", {**news, "country": "us"})
    # Same parameters on another provider or endpoint are different requests.
    assert key("gnews", {"q": "cloud"}) != key("newsapi", {"q": "cloud"})
    assert key("gnews", {"q": "cloud"}, url="https://gnews.io/api/v4/search") != key(
        "gnews", {"q": "cloud"}, url="https://gnews.io/api/v4/top-headlines"
    )


def test_time_parameters_are_bucketed_by_ttl():
    def tn(after):
        return key("the_news_api", {"search": "cloud", "published_after": after})

    # TTL 2 hours: 10:05 and 11:55 share a bucket; 12:00 starts the next one.
    assert tn("2026-10-14T10:05:00") == tn("2026-10-14T11:55:00")
    assert tn("2026-10-14T10:05:00") != tn("2026-10-14T12:00:00")
    assert tn("not a date") is None  # unparsable: never shared
    exa = lambda d: key(  # noqa: E731
        "exa",
        method="POST",
        body={"query": "latest news about seo", "type": "auto", "startPublishedDate": d},
    )
    assert exa("2026-10-14T10:00:00.000Z") == exa("2026-10-14T11:59:59.000Z")


def test_unknown_parameters_and_methods_are_not_shared():
    assert key("google_trends", {"geo": "US", "debug": "1"}) is None
    assert key("exa", method="POST", body={"query": "x", "surprise": True}) is None
    assert key("google_trends", {"geo": "US"}, method="POST", body={"geo": "US"}) is None
    assert key("google_trends", {"geo": "US"}, method="DELETE") is None
    assert key("rss", {"x": "1"}) is None  # no policy: organization feeds are never shared


def test_ttl_overrides(monkeypatch):
    monkeypatch.setattr(get_settings(), "provider_cache_ttls", {"exa": 86_400, "google_news": 60})
    assert prepare("exa", "POST", "https://api.exa.ai/search", body={"query": "x"}).ttl == 86_400
    assert prepare("google_news", "GET", "https://news.google.com/rss", {"gl": "US"}).ttl == 60
    assert prepare("hacker_news", "GET", "https://hn.algolia.com/x", {"tags": "story"}).ttl == 1200


# --- Coverage: every adapter's requests go through the cache -----------------------------

ALL_KEYS = Settings(
    _env_file=None,
    reddit_client_id="rid",
    reddit_client_secret="rsecret",
    news_api_key="na",
    gnews_api_key="gn",
    world_news_api_key="wn",
    newsdata_api_key="nd",
    the_news_api_key="tn",
    exa_api_key="ex",
    serp_api_key="sp",
    apitube_news_api_key="at",
    x_api_key="xk",
    x_api_secret="xs",
    instagram_access_token="EAAB" + "t" * 60,
    instagram_business_account_id="1784",
)


@pytest.mark.parametrize(
    "source",
    sorted(k for k, s in SOURCES.items() if k not in ("rss", "linkedin")),
)
async def test_every_provider_request_is_shareable(source, monkeypatch):
    monkeypatch.setattr("app.sources.reddit.PUBLIC_DELAY_SECONDS", 0)
    monkeypatch.setattr("app.sources.additional_news.NEWSDATA_REQUEST_GAP", 0)
    monkeypatch.setattr("app.sources.additional_news.WORLD_NEWS_REQUEST_GAP", 0)
    monkeypatch.setattr("app.sources.additional_news.THE_NEWS_API_REQUEST_GAP", 0)
    monkeypatch.setattr("app.sources.news_apis.GNEWS_REQUEST_GAP", 0)
    monkeypatch.setattr("app.sources.exa.REQUEST_GAP", 0)
    monkeypatch.setattr("app.sources.instagram.HASHTAG_GAP", 0)
    monkeypatch.setattr("app.sources.google_trends_tech.MARKET_GAP", 0)
    try:
        await run_source(source, settings=ALL_KEYS)
    except SourceError:
        pass  # unknown hosts answer 404 in the fake internet; the request still counted
    stats = cache_stats.snapshot().get(source, {})
    assert "uncacheable" not in stats, stats
    assert stats.get("miss", 0) >= 1, stats


async def test_rss_feeds_never_touch_the_shared_cache(postgres_cache, db, monkeypatch):
    postgres_cache(*SOURCES)  # even if every provider were allowed
    net = FakeInternet()
    locations, _ = resolve_markets(["USA"])

    async def resolver(host):
        return ["93.184.216.34"]

    async with httpx.AsyncClient(transport=httpx.MockTransport(net.handler)) as client:
        ctx = SourceContext(
            client=client,
            settings=Settings(_env_file=None),
            inputs=SourceInputs(
                locations=locations, keywords=[], rss_feeds=["https://blog.example.com/feed"]
            ),
            since=SINCE - timedelta(hours=48),
            resolver=resolver,
        )
        await SOURCES["rss"].collect(ctx)
    assert "rss" not in cache_stats.snapshot()
    assert await db.scalar(select(text("count(*)")).select_from(ProviderCache)) == 0


# --- Persistence ------------------------------------------------------------------------


async def rows(db):
    return list((await db.execute(select(ProviderCache))).scalars())


async def test_memory_backend_stores_nothing(db):
    _, net = await run_source("google_trends")
    assert len(net.calls) == 1 and await rows(db) == []


async def test_responses_survive_a_process_restart(postgres_cache, db):
    postgres_cache("google_trends", "hacker_news")
    first, net = await run_source("google_trends")
    assert len(net.calls) == 1
    request_cache.clear()  # the process restarted (or Render slept)
    second, net2 = await run_source("google_trends")
    assert net2.calls == []  # served from Postgres
    assert [i.title for i in second] == [i.title for i in first]
    assert cache_stats.snapshot()["google_trends"]["db_hit"] == 1
    stored = await rows(db)
    assert {r.source for r in stored} == {"google_trends"}
    assert all(len(r.key) == 64 and r.expires_at > datetime.now(UTC) for r in stored)


async def test_providers_must_be_opted_in_and_some_never_are(postgres_cache, db):
    postgres_cache("hacker_news", "reddit", "x", "instagram")  # google_trends not listed
    await run_source("google_trends")
    await run_source("reddit", settings=ALL_KEYS)
    await run_source("x", settings=ALL_KEYS)
    await run_source("instagram", settings=ALL_KEYS)
    assert await rows(db) == []  # deletion obligations: memory only, whatever the list says


async def test_no_secrets_at_rest(postgres_cache, db):
    postgres_cache("newsdata", "gnews", "exa", "the_news_api", "serpapi_news")
    secrets = {
        "newsdata_api_key": "ND-SECRET-123",
        "gnews_api_key": "GN-SECRET-456",
        "exa_api_key": "EX-SECRET-789",
        "the_news_api_key": "TN-SECRET-000",
        "serp_api_key": "SP-SECRET-111",
    }
    settings = Settings(_env_file=None, **secrets)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [], "articles": [], "data": []})

    net = FakeInternet()
    net.handler = handler
    for source in ("newsdata", "gnews", "exa", "the_news_api", "serpapi_news"):
        try:
            await run_source(source, settings=settings, net=net)
        except SourceError:
            pass
    dump = (await db.execute(text("SELECT row_to_json(p)::text FROM provider_cache p"))).scalars()
    everything = "\n".join(dump)
    assert everything, "expected stored responses"
    for value in secrets.values():
        assert value not in everything


async def test_errors_and_oversized_responses_are_not_stored(postgres_cache, db, monkeypatch):
    postgres_cache("google_trends")
    net = FakeInternet()
    net.fail("trends.google.com", 503)
    with pytest.raises(SourceError):
        await run_source("google_trends", net=net)
    assert await rows(db) == []  # the lease row was released too

    request_cache.clear()
    monkeypatch.setattr(get_settings(), "provider_cache_max_bytes", 100)
    await run_source("google_trends")  # the feed is larger than 100 bytes
    assert await rows(db) == []


async def test_expired_responses_are_fetched_again(postgres_cache, db):
    postgres_cache("google_trends")
    await run_source("google_trends")
    await db.execute(
        update(ProviderCache).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db.commit()
    request_cache.clear()
    _, net = await run_source("google_trends")
    assert len(net.calls) == 1
    [row] = await rows(db)
    await db.refresh(row)
    assert row.expires_at > datetime.now(UTC)


# --- Leases --------------------------------------------------------------------------


def trends_request():
    return prepare("google_trends", "GET", "https://trends.google.com/trending/rss", {"geo": "US"})


async def test_concurrent_misses_in_different_processes_fetch_once(postgres_cache, db):
    postgres_cache("google_trends")
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.6)  # the other "process" polls meanwhile
        return httpx.Response(200, text="<rss/>", headers={"content-type": "application/rss+xml"})

    # _load is the per-process level-2 path; calling it twice concurrently is
    # what two Render workers missing the same key at once look like.
    prepared = trends_request()
    a, b = await asyncio.gather(
        provider_cache._load(prepared, fetch), provider_cache._load(prepared, fetch)
    )
    assert calls == 1
    assert a.text == b.text == "<rss/>"
    assert cache_stats.snapshot()["google_trends"]["lease_wait"] == 1


async def test_abandoned_lease_is_reclaimed(postgres_cache, db):
    postgres_cache("google_trends")
    prepared = trends_request()
    # A worker took the lease and was killed before storing anything.
    db.add(
        ProviderCache(
            key=prepared.key,
            source="google_trends",
            lease_owner=uuid.uuid4(),
            lease_until=datetime.now(UTC) - timedelta(seconds=5),
        )
    )
    await db.commit()

    async def fetch():
        return httpx.Response(200, text="<rss/>")

    response = await provider_cache._load(prepared, fetch)
    assert response.text == "<rss/>"
    assert "lease_wait" not in cache_stats.snapshot()["google_trends"]
    [row] = await rows(db)
    await db.refresh(row)
    assert row.body == b"<rss/>" and row.lease_owner is None


async def test_a_hung_lease_only_delays_other_workers_briefly(postgres_cache, db, monkeypatch):
    postgres_cache("google_trends")
    monkeypatch.setattr(get_settings(), "provider_cache_wait_seconds", 0.5)
    prepared = trends_request()
    db.add(
        ProviderCache(
            key=prepared.key,
            source="google_trends",
            lease_owner=uuid.uuid4(),
            lease_until=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    await db.commit()

    async def fetch():
        return httpx.Response(200, text="<rss/>")

    assert (await provider_cache._load(prepared, fetch)).text == "<rss/>"
    assert cache_stats.snapshot()["google_trends"]["lease_timeout"] == 1


# --- Database failures and clean-up -----------------------------------------------------


async def test_database_failure_policy(postgres_cache, monkeypatch):
    postgres_cache("google_trends")

    async def broken(*args, **kwargs):
        raise OSError("database unreachable")

    monkeypatch.setattr(store, "load", broken)

    async def fetch():
        return httpx.Response(200, text="live")

    prepared = trends_request()
    assert (await provider_cache._load(prepared, fetch)).text == "live"  # default: fetch
    monkeypatch.setattr(get_settings(), "provider_cache_on_db_error", "skip")
    with pytest.raises(SourceError) as exc:
        await provider_cache._load(prepared, fetch)
    assert exc.value.kind == SourceErrorKind.UNAVAILABLE


async def test_prune_and_purge(db, monkeypatch):
    now = datetime.now(UTC)

    def row(name, *, expires=None, body=b"x", lease=None):
        return ProviderCache(
            key=name.ljust(64, "0"),
            source="google_trends",
            body=body,
            expires_at=expires,
            lease_until=lease,
            created_at=now - timedelta(hours=2),
        )

    db.add_all(
        [
            row("a", expires=now + timedelta(hours=1)),  # fresh
            row("b", expires=now - timedelta(hours=1)),  # stale, still within 6h
            row("c", expires=now - timedelta(hours=7)),  # past the stale window
            row("d", body=None, lease=now - timedelta(hours=2)),  # dead lease
        ]
    )
    await db.commit()
    assert await store.prune(stale_seconds=6 * 3600, batch=1) == 2
    assert sorted(r.key[0] for r in await rows(db)) == ["a", "b"]
    assert await store.purge("google_trends") == 2
    assert await rows(db) == []


async def test_housekeeping_prunes_the_cache(db):
    from app.services.housekeeping import run_housekeeping

    db.add(
        ProviderCache(
            key="e" * 64,
            source="gnews",
            body=b"x",
            expires_at=datetime.now(UTC) - timedelta(days=2),
        )
    )
    await db.commit()
    result = await run_housekeeping()
    assert result["provider_cache"] == 1


# --- Tokens and tenants ------------------------------------------------------------------


async def test_oauth_tokens_are_reused_not_refetched():
    net = FakeInternet()
    await run_source("x", settings=ALL_KEYS, net=net)
    await run_source("x", settings=ALL_KEYS, keywords=["other"], net=net)
    assert net.calls.count("api.x.com/oauth2/token") == 1
    await run_source("reddit", settings=ALL_KEYS, net=net)
    await run_source("reddit", settings=ALL_KEYS, keywords=["other"], net=net)
    assert net.calls.count("www.reddit.com/api/v1/access_token") == 1


async def test_organizations_share_persisted_public_data_but_not_results(
    client, postgres_cache, monkeypatch
):
    """Org B runs after a restart: no provider calls, its own trends and scores."""
    from app.workers import trend_tasks
    from tests.conftest import create_org, register
    from tests.test_trends_api import API, discover, setup
    from tests.test_trends_api import internet as _internet  # noqa: F401

    postgres_cache("google_trends", "google_news", "hacker_news")
    net = FakeInternet()
    net.fail("www.reddit.com", 429)
    monkeypatch.setattr(
        trend_tasks,
        "http_client_factory",
        lambda s: httpx.AsyncClient(transport=httpx.MockTransport(net.handler)),
    )
    admin, _ = await setup(client)
    await discover(admin)
    public_calls = [c for c in net.calls if "reddit" not in c]

    request_cache.clear()  # restart between the two organizations' runs
    other = await register(client, "b@b.example.com")
    org_b = await create_org(other, "B Co")
    await other.patch(
        f"/api/v1/organizations/{org_b['id']}/settings",
        json={"target_markets": ["USA"], "tracked_keywords": ["GPT-6"]},
    )
    before = len([c for c in net.calls if "reddit" not in c])
    run = await discover(other)
    assert run["status"] == "succeeded"
    assert len([c for c in net.calls if "reddit" not in c]) == before == len(public_calls)

    a_items = (await admin.get(API)).json()["items"]
    b_items = (await other.get(API)).json()["items"]
    assert b_items and not {t["id"] for t in a_items} & {t["id"] for t in b_items}
