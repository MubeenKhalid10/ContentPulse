from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.config import Settings
from app.sources import SOURCES
from app.sources.base import (
    SourceContext,
    SourceError,
    SourceErrorKind,
    SourceInputs,
    request_cache,
)
from app.sources.google_trends import parse_traffic
from app.sources.locations import resolve_markets
from tests.trend_fixtures import FakeInternet

NO_KEYS = Settings(_env_file=None)


async def public_resolver(host: str) -> list[str]:
    return ["93.184.216.34"]


async def collect(
    key: str, *, settings: Settings = NO_KEYS, inputs: SourceInputs | None = None, net=None
):
    request_cache.clear()  # each call simulates an independent scenario
    net = net or FakeInternet()
    locations, _ = resolve_markets(["USA"])
    inputs = inputs or SourceInputs(locations=locations, keywords=["automation"])
    async with httpx.AsyncClient(transport=httpx.MockTransport(net.handler)) as client:
        ctx = SourceContext(
            client=client,
            settings=settings,
            inputs=inputs,
            since=datetime.now(UTC) - timedelta(hours=48),
            resolver=public_resolver,
        )
        items = await SOURCES[key].collect(ctx)
    return items, ctx, net


def test_every_source_reports_configuration_without_keys():
    inputs = SourceInputs(locations=resolve_markets([])[0], keywords=[])
    states = {k: s.configuration(NO_KEYS, inputs) for k, s in SOURCES.items()}
    assert {k for k, c in states.items() if c.configured} == {
        "google_trends",
        "google_news",
        "hacker_news",
        "reddit",
    }
    assert states["newsapi"].missing == ("NEWS_API_KEY",)
    assert states["instagram"].missing == (
        "INSTAGRAM_ACCESS_TOKEN",
        "INSTAGRAM_BUSINESS_ACCOUNT_ID",
    )
    assert states["linkedin"].configured is False and "partners" in states["linkedin"].note
    assert "feed" in states["rss"].note.lower()


@pytest.mark.parametrize(
    ("raw", "value"),
    [("200K+", 200_000), ("1M+", 1_000_000), ("2,000+", 2000), ("100+", 100), (None, None)],
)
def test_parse_traffic(raw, value):
    assert parse_traffic(raw) == value


async def test_google_trends():
    items, ctx, _ = await collect("google_trends")
    first = items[0]
    assert first.topic == "openai gpt-6"
    assert first.engagement == 200_000 and first.engagement_label == "200K+ searches"
    assert first.location == "US"
    assert first.description == "OpenAI launches GPT-6 for enterprise automation"
    assert "trends.google.com/trends/explore" in first.source_url


async def test_google_trends_global_falls_back_with_warning():
    inputs = SourceInputs(locations=resolve_markets([])[0], keywords=[])
    _, ctx, net = await collect("google_trends", inputs=inputs)
    assert any("United States" in w for w in ctx.warnings)
    assert any("trends.google.com" in c for c in net.calls)


async def test_google_news_strips_publisher_and_old_items():
    items, _, _ = await collect("google_news")
    titles = {i.title for i in items}
    assert "OpenAI GPT-6 arrives with autonomous agents" in titles
    assert not any("Old story" in t for t in titles)  # outside the 48h window
    reuters = next(i for i in items if i.author == "Reuters")
    assert reuters.location == "US"


async def test_hacker_news_strips_prefix_and_keeps_points():
    items, _, _ = await collect("hacker_news")
    rust = next(i for i in items if "Rust" in i.title)
    assert rust.title == "A tiny Rust database for embedded devices"
    assert rust.source_url == "https://news.ycombinator.com/item?id=102"  # no article URL
    gpt = next(i for i in items if i.source_item_id == "101")
    assert gpt.engagement == 450 and gpt.engagement_label == "450 points · 230 comments"


async def test_reddit_oauth_skips_nsfw_and_stickied():
    settings = Settings(_env_file=None, reddit_client_id="id", reddit_client_secret="secret")
    items, _, net = await collect("reddit", settings=settings)
    assert {i.source_item_id for i in items} == {"abc1"}
    assert items[0].engagement == 3400
    assert any("oauth.reddit.com" in c for c in net.calls)


async def test_reddit_public_rss_without_keys(monkeypatch):
    monkeypatch.setattr("app.sources.reddit.PUBLIC_DELAY_SECONDS", 0)
    items, _, net = await collect("reddit")
    assert items[0].source_item_id == "rss1"  # "t3_" prefix removed
    assert items[0].engagement is None
    assert not any("oauth" in c for c in net.calls)


async def test_reddit_rate_limit_is_a_typed_error(monkeypatch):
    monkeypatch.setattr("app.sources.reddit.PUBLIC_DELAY_SECONDS", 0)
    net = FakeInternet()
    net.fail("www.reddit.com", 429)
    with pytest.raises(SourceError) as exc:
        await collect("reddit", net=net)
    assert exc.value.kind == SourceErrorKind.RATE_LIMITED
    assert len(net.calls) == 1  # stops after the first 429


async def test_rss_feed_and_ssrf_guard():
    locations, _ = resolve_markets(["USA"])
    inputs = SourceInputs(
        locations=locations,
        keywords=[],
        rss_feeds=["https://blog.example.com/feed", "http://169.254.169.254/latest/"],
    )
    items, ctx, net = await collect("rss", inputs=inputs)
    assert [i.title for i in items] == ["Why GPT-6 changes back-office automation"]
    assert items[0].description == "Agents everywhere."
    assert not any("169.254" in c for c in net.calls)  # private address never fetched
    assert any("not a public address" in w for w in ctx.warnings)


async def test_newsapi_and_gnews_with_keys():
    settings = Settings(_env_file=None, news_api_key="k1", gnews_api_key="k2")
    news, _, _ = await collect("newsapi", settings=settings)
    assert [i.title for i in news].count("GPT-6 sets new bar for enterprise AI") >= 1
    assert all(i.title != "[Removed]" for i in news)
    gnews, _, _ = await collect("gnews", settings=settings)
    assert gnews[0].author == "G Example"


async def test_keyed_sources_refuse_to_run_without_keys():
    for key in ("newsapi", "gnews", "x", "instagram", "linkedin"):
        with pytest.raises(SourceError) as exc:
            await collect(key)
        assert exc.value.kind == SourceErrorKind.NOT_CONFIGURED, key


async def test_x_exchanges_key_and_secret_for_bearer():
    settings = Settings(_env_file=None, x_api_key="key", x_api_secret="secret")
    items, _, net = await collect("x", settings=settings)
    assert any(c.endswith("/oauth2/token") for c in net.calls)
    item = items[0]
    assert item.topic == "automation"
    assert item.engagement == 900 + 120 + 40 + 5 + 11
    assert item.engagement_label == "2 posts · 1.1K interactions"


async def test_instagram_and_expired_token():
    settings = Settings(
        _env_file=None, instagram_access_token="t", instagram_business_account_id="1"
    )
    items, _, _ = await collect("instagram", settings=settings)
    assert items[0].topic == "#automation" and items[0].engagement == 1280

    net = FakeInternet()
    net.fail("graph.facebook.com", 400, '{"error": {"type": "OAuthException", "code": 190}}')
    with pytest.raises(SourceError) as exc:
        await collect("instagram", settings=settings, net=net)
    assert exc.value.kind == SourceErrorKind.AUTH


async def test_auth_errors_are_classified():
    net = FakeInternet()
    net.fail("newsapi.org", 401, '{"status":"error","code":"apiKeyInvalid"}')
    with pytest.raises(SourceError) as exc:
        await collect("newsapi", settings=Settings(_env_file=None, news_api_key="bad"), net=net)
    assert exc.value.kind == SourceErrorKind.AUTH


async def test_request_cache_shares_inflight_and_remembers_failures():
    import asyncio

    from app.sources.base import RequestCache

    cache = RequestCache()
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return httpx.Response(200, text="ok")

    results = await asyncio.gather(*(cache.get_or_fetch("k", fetch) for _ in range(5)))
    assert calls == 1 and all(r.text == "ok" for r in results)

    async def fail():
        nonlocal calls
        calls += 1
        raise SourceError(SourceErrorKind.RATE_LIMITED, "slow down")

    for _ in range(3):
        with pytest.raises(SourceError):
            await cache.get_or_fetch("bad", fail)
    assert calls == 2  # the failure is remembered instead of retried immediately
