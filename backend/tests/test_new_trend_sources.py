"""Google Trends · Technology (trendspy) and TheNewsAPI adapters."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.config import Settings
from app.services.trends.scoring import MentionView, growth, popularity
from app.sources import SOURCES, additional_news, google_trends_tech
from app.sources.additional_news import plan_queries
from app.sources.base import (
    SourceContext,
    SourceError,
    SourceErrorKind,
    SourceInputs,
    request_cache,
)
from app.sources.locations import resolve_markets

STARTED = int(datetime(2026, 10, 12, 9, tzinfo=UTC).timestamp())


@pytest.fixture(autouse=True)
def no_gaps(monkeypatch):
    monkeypatch.setattr(additional_news, "THE_NEWS_API_REQUEST_GAP", 0)
    monkeypatch.setattr(google_trends_tech, "MARKET_GAP", 0)
    request_cache.clear()
    yield
    request_cache.clear()


async def collect(key: str, settings: Settings, handler=None, markets=("USA",), keywords=()):
    locations, _ = resolve_markets(list(markets))
    transport = httpx.MockTransport(handler or (lambda r: httpx.Response(404)))
    async with httpx.AsyncClient(transport=transport) as client:
        ctx = SourceContext(
            client=client,
            settings=settings,
            inputs=SourceInputs(locations=locations, keywords=list(keywords)),
            since=datetime.now(UTC) - timedelta(hours=48),
        )
        return await SOURCES[key].collect(ctx), ctx


# --- Google Trends · Technology -------------------------------------------------------


async def test_tech_trends_become_items_per_market(monkeypatch):
    calls: list[str] = []

    def fake_fetch(geo: str, hours: int = 24):
        calls.append(geo)
        return [
            {
                "keyword": "iPhone 18",
                "volume": 200_000,
                "growth_pct": 1000,
                "started": STARTED,
                "related": ["iPhone 18 Pro", "apple event"],
                "topics": ["Technology"],
            },
            {"keyword": "  ", "volume": 10},  # ignored
        ]

    monkeypatch.setattr(google_trends_tech, "fetch_tech_trends", fake_fetch)
    items, ctx = await collect(
        "google_trends_tech", Settings(_env_file=None), markets=["USA", "UK"]
    )

    assert calls == ["US", "GB"]
    assert len(items) == 2 and not ctx.warnings
    item = items[0]
    assert item.source == "google_trends_tech"
    assert item.title == item.topic == "iPhone 18"
    assert item.category == "Technology" and item.location == "US"
    assert item.engagement == 200_000 and item.engagement_label == "200K+ searches"
    assert item.published_at == datetime.fromtimestamp(STARTED, UTC)
    assert item.source_item_id == "US:iphone 18:2026-10-12"
    assert item.keywords == ["iphone 18 pro", "apple event"]
    assert "q=iPhone%2018" in item.source_url and "geo=US" in item.source_url


async def test_tech_trends_failure_is_a_source_error(monkeypatch):
    def broken(geo: str, hours: int = 24):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(google_trends_tech, "fetch_tech_trends", broken)
    with pytest.raises(SourceError) as err:
        await collect("google_trends_tech", Settings(_env_file=None), markets=["USA", "UK"])
    assert err.value.kind == SourceErrorKind.RATE_LIMITED


def test_tech_searches_score_like_google_trends():
    now = datetime.now(UTC)
    mention = MentionView("google_trends_tech", "iPhone 18", 200_000, now, now, "US", None)
    assert "searches on Google Trends (Technology)" in popularity([mention])["detail"]
    assert growth([mention], now)["score"] >= 70


# --- TheNewsAPI -----------------------------------------------------------------------

NEWS_KEY = Settings(_env_file=None, the_news_api_key="tn-key")


def test_the_news_api_needs_its_key_and_keywords():
    inputs = SourceInputs(locations=resolve_markets([])[0], keywords=["cloud"])
    source = SOURCES["the_news_api"]
    assert source.configuration(Settings(_env_file=None), inputs).missing == ("THE_NEWS_API_KEY",)
    assert source.configuration(NEWS_KEY, inputs).configured
    empty = SourceInputs(locations=resolve_markets([])[0], keywords=[])
    assert not source.configuration(NEWS_KEY, empty).configured


def test_phrases_are_quoted_and_joined_with_pipes():
    plan = plan_queries(
        ["agentic AI", "cloud", "agentic ai"], 200, joiner=" | ", quote_phrases=True
    )
    assert plan.queries == ['"agentic AI" | cloud']


async def test_the_news_api_searches_and_maps_articles():
    seen: list[httpx.QueryParams] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.thenewsapi.com"
        seen.append(request.url.params)
        return httpx.Response(
            200,
            json={
                "meta": {"found": 2, "returned": 2, "limit": 3, "page": 1},
                "data": [
                    {
                        "uuid": "u-1",
                        "title": "Agentic AI goes mainstream",
                        "description": "Teams adopt agents.",
                        "keywords": "AI, agents",
                        "url": "https://news.example/agentic",
                        "published_at": "2026-10-12T08:00:00.000000Z",
                        "source": "news.example",
                        "categories": ["tech"],
                        "locale": "us",
                    },
                    {"uuid": "u-2", "title": "No link"},  # skipped: no url
                ],
            },
        )

    items, _ = await collect("the_news_api", NEWS_KEY, handler, keywords=["agentic AI", "cloud"])
    [params] = seen
    assert params["api_token"] == "tn-key"
    assert params["search"] == '"agentic AI" | cloud'
    assert params["limit"] == "3" and params["locale"] == "us" and params["language"] == "en"
    assert "T" in params["published_after"]
    [item] = items
    assert item.source == "the_news_api" and item.source_item_id == "u-1"
    assert item.category == "Tech" and item.location == "US"
    assert item.keywords == ["ai", "agents"] and item.author == "news.example"
    assert item.published_at is not None


async def test_the_news_api_usage_limit_is_rate_limited():
    with pytest.raises(SourceError) as err:
        await collect(
            "the_news_api",
            NEWS_KEY,
            lambda r: httpx.Response(402, json={"error": {"code": "usage_limit_reached"}}),
            keywords=["cloud"],
        )
    assert err.value.kind == SourceErrorKind.RATE_LIMITED
