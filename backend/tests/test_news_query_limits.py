"""NewsData.io and World News API: keyword searches stay within the providers'
100-character limits, are split into valid batches, and merge without duplicates."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.config import Settings
from app.sources import SOURCES, additional_news
from app.sources.additional_news import (
    NEWSDATA_QUERY_LIMIT,
    WORLD_NEWS_TEXT_LIMIT,
    plan_queries,
)
from app.sources.base import (
    SourceContext,
    SourceError,
    SourceErrorKind,
    SourceInputs,
    request_cache,
)
from app.sources.locations import resolve_markets

KEYS = Settings(_env_file=None, newsdata_api_key="nd-key", world_news_api_key="wn-key")

# Realistic organization keywords: together far past 100 characters.
LONG_KEYWORDS = [
    "artificial intelligence governance",
    "cloud security posture management",
    "incident response planning",
    "small business cybersecurity",
    "security awareness training",
    "compliance automation",
]


@pytest.fixture(autouse=True)
def no_gaps(monkeypatch):
    monkeypatch.setattr(additional_news, "NEWSDATA_REQUEST_GAP", 0)
    monkeypatch.setattr(additional_news, "WORLD_NEWS_REQUEST_GAP", 0)
    request_cache.clear()
    yield
    request_cache.clear()


class FakeNewsApis:
    """Answers both providers; enforces their real length limits."""

    def __init__(self, responses: dict[int, httpx.Response] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.responses = responses or {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if len(self.requests) in self.responses:
            return self.responses[len(self.requests)]
        params = request.url.params
        if request.url.host == "newsdata.io":
            q = params.get("q", "")
            if len(q) > NEWSDATA_QUERY_LIMIT:
                return httpx.Response(422, json={"message": "Query cannot exceed 100 characters"})
            return httpx.Response(200, json={"results": _articles(q, link_key="link")})
        if request.url.host == "api.worldnewsapi.com":
            text = params.get("text")
            if text is not None and (not text or len(text) > WORLD_NEWS_TEXT_LIMIT):
                return httpx.Response(400, json={"message": "text too long or empty"})
            return httpx.Response(200, json={"news": _articles(text or "latest", link_key="url")})
        return httpx.Response(404)


def _articles(query: str, *, link_key: str) -> list[dict]:
    """One article unique to this query, plus one every query returns."""
    first = query.split(" OR ")[0]
    return [
        {
            "id": f"id-{first}",
            "title": f"News about {first}",
            link_key: f"https://news.example/{first}",
        },
        {
            "id": "shared",
            "title": "A story every search finds",
            link_key: "https://news.example/shared",
        },
    ]


async def collect(key: str, keywords: list[str], net: FakeNewsApis):
    locations, _ = resolve_markets(["USA"])
    async with httpx.AsyncClient(transport=httpx.MockTransport(net.handler)) as client:
        ctx = SourceContext(
            client=client,
            settings=KEYS,
            inputs=SourceInputs(locations=locations, keywords=keywords),
            since=datetime.now(UTC) - timedelta(hours=48),
        )
        items = await SOURCES[key].collect(ctx)
    return items, ctx


# --- Planning -----------------------------------------------------------------------


def test_exactly_at_the_limit_is_one_query_and_one_more_char_splits():
    a, b = "x" * 48, "y" * 48  # 48 + len(" OR ") + 48 = 100
    assert plan_queries([a, b], 100).queries == [f"{a} OR {b}"]
    a2 = "x" * 49  # 101: must split, never truncate
    assert plan_queries([a2, b], 100).queries == [a2, b]


def test_every_query_fits_and_keeps_every_keyword_whole():
    plan = plan_queries(LONG_KEYWORDS, 100)
    assert len(plan.queries) == 2
    assert all(len(q) <= 100 for q in plan.queries)
    searched = [term for q in plan.queries for term in q.split(" OR ")]
    assert sorted(searched) == sorted(LONG_KEYWORDS)  # every keyword, none cut
    assert plan.queries[0].startswith(LONG_KEYWORDS[0])  # top priority goes first
    assert not plan.shortened and not plan.dropped


def test_overlong_single_keyword_keeps_leading_whole_words():
    long_term = " ".join(["cybersecurity"] * 10)  # 139 characters
    plan = plan_queries([long_term], 100)
    assert plan.shortened == [long_term]
    [query] = plan.queries
    assert len(query) <= 100 and query.split() == ["cybersecurity"] * 7

    exact = "a" * 100
    assert plan_queries([exact], 100).queries == [exact]

    unbreakable = "z" * 150  # no whole word fits: skipped, never chopped
    plan = plan_queries([unbreakable, "automation"], 100)
    assert plan.queries == ["automation"] and plan.dropped == [unbreakable]


def test_keywords_are_cleaned_and_deduplicated():
    plan = plan_queries(["  Automation ", "automation", "", "cloud   security"], 100)
    assert plan.queries == ["Automation OR cloud security"]


def test_requests_per_run_are_capped():
    keywords = [f"{'k' * 60}{i}" for i in range(6)]  # each needs its own query
    plan = plan_queries(keywords, 100, max_queries=3)
    assert len(plan.queries) == 3
    assert plan.dropped == keywords[3:]


# --- NewsData.io --------------------------------------------------------------------


async def test_newsdata_splits_long_keywords_and_merges_without_duplicates():
    net = FakeNewsApis()
    items, ctx = await collect("newsdata", LONG_KEYWORDS, net)

    queries = [r.url.params["q"] for r in net.requests]
    assert len(queries) == 2 and all(len(q) <= 100 for q in queries)
    assert all(r.url.params["country"] == "us" for r in net.requests)
    ids = [i.source_item_id for i in items]
    assert ids.count("shared") == 1  # found by both searches, kept once
    assert len(ids) == 3
    assert ctx.warnings == []


async def test_newsdata_short_keywords_make_one_request_as_before():
    net = FakeNewsApis()
    items, _ = await collect("newsdata", ["automation", "ai"], net)
    assert [r.url.params["q"] for r in net.requests] == ["automation OR ai"]
    assert len(items) == 2


async def test_newsdata_without_keywords_keeps_the_fallback_query():
    net = FakeNewsApis()
    await collect("newsdata", [], net)
    assert [r.url.params["q"] for r in net.requests] == ["technology"]


async def test_newsdata_rate_limit_stops_further_requests():
    net = FakeNewsApis({1: httpx.Response(429)})
    with pytest.raises(SourceError) as exc:
        await collect("newsdata", LONG_KEYWORDS, net)
    assert exc.value.kind == SourceErrorKind.RATE_LIMITED
    assert len(net.requests) == 1  # the second batch would only burn quota


async def test_newsdata_keeps_results_when_a_later_batch_is_rate_limited():
    net = FakeNewsApis({2: httpx.Response(429)})
    items, ctx = await collect("newsdata", LONG_KEYWORDS, net)
    assert len(items) == 2
    assert any("Rate limited" in w for w in ctx.warnings)


# --- World News API -----------------------------------------------------------------


async def test_world_news_splits_text_and_merges_without_duplicates():
    net = FakeNewsApis()
    items, ctx = await collect("world_news", LONG_KEYWORDS, net)

    texts = [r.url.params["text"] for r in net.requests]
    assert len(texts) == 2 and all(len(t) <= 100 for t in texts)
    assert [i.source_item_id for i in items].count("shared") == 1
    assert ctx.warnings == []


async def test_world_news_omits_text_when_there_are_no_keywords():
    net = FakeNewsApis()
    items, _ = await collect("world_news", ["  ", ""], net)
    [request] = net.requests
    assert "text" not in request.url.params
    assert request.url.params["language"] == "en" and items


async def test_world_news_warns_about_shortened_keywords():
    long_term = " ".join(["compliance"] * 12)  # 131 characters
    net = FakeNewsApis()
    _, ctx = await collect("world_news", [long_term], net)
    [request] = net.requests
    assert len(request.url.params["text"]) <= 100
    assert any("shortened" in w for w in ctx.warnings)


async def test_world_news_auth_error_is_reported_once():
    net = FakeNewsApis({1: httpx.Response(401)})
    with pytest.raises(SourceError) as exc:
        await collect("world_news", LONG_KEYWORDS, net)
    assert exc.value.kind == SourceErrorKind.AUTH
    assert len(net.requests) == 1
