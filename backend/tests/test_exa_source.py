"""Exa web search source: the recommended request shape, mapping, and limits."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.config import Settings
from app.sources import SOURCES, exa
from app.sources.base import (
    SourceContext,
    SourceError,
    SourceErrorKind,
    SourceInputs,
    request_cache,
)
from app.sources.locations import resolve_markets

KEY = Settings(_env_file=None, exa_api_key="exa-key")


@pytest.fixture(autouse=True)
def no_gaps(monkeypatch):
    monkeypatch.setattr(exa, "REQUEST_GAP", 0)
    request_cache.clear()
    yield
    request_cache.clear()


def result(n: int, url: str | None = None) -> dict:
    return {
        "id": f"https://news.example/{n}",
        "url": url or f"https://news.example/{n}",
        "title": f"Story {n}",
        "publishedDate": "2026-10-12T08:00:00.000Z",
        "author": "Ada Writer",
        "highlights": [f"First key passage {n}.", "  ", f"Second passage {n}."],
    }


async def collect(handler, keywords=(), markets=("USA",), settings=KEY):
    locations, _ = resolve_markets(list(markets))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ctx = SourceContext(
            client=client,
            settings=settings,
            inputs=SourceInputs(locations=locations, keywords=list(keywords)),
            since=datetime(2026, 10, 11, 6, tzinfo=UTC),
        )
        return await SOURCES["exa"].collect(ctx), ctx


def test_exa_needs_its_key_and_something_to_search():
    inputs = SourceInputs(locations=resolve_markets([])[0], keywords=["cloud"])
    assert SOURCES["exa"].configuration(Settings(_env_file=None), inputs).missing == (
        "EXA_API_KEY",
    )
    assert SOURCES["exa"].configuration(KEY, inputs).configured
    # No keywords, services or industry: nothing to search (no generic fallback).
    empty = SourceInputs(locations=resolve_markets([])[0], keywords=[])
    config = SOURCES["exa"].configuration(KEY, empty)
    assert not config.configured and "keywords" in config.note


async def test_sends_the_recommended_request_per_keyword():
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and str(request.url) == exa.SEARCH_URL
        assert request.headers["x-api-key"] == "exa-key"
        bodies.append(json.loads(request.content))
        n = len(bodies)
        # The second search also finds the first story: it must appear once.
        return httpx.Response(200, json={"results": [result(n), result(1)]})

    keywords = ["agentic AI", "cloud security", "AGENTIC ai", "zero trust", "edge AI"]
    items, ctx = await collect(handler, keywords)

    assert [b["query"] for b in bodies] == [
        "latest news about agentic AI",
        "latest news about cloud security",
        "latest news about zero trust",
    ]
    assert bodies[0] == {
        "query": "latest news about agentic AI",
        "type": "auto",
        "contents": {"highlights": True},
        "startPublishedDate": "2026-10-11T06:00:00.000Z",
        "userLocation": "US",
    }
    assert ctx.warnings == ["Exa web search: skipped keywords this run: edge AI"]
    assert [i.title for i in items] == ["Story 1", "Story 2", "Story 3"]
    first = items[0]
    assert first.source == "exa" and first.author == "Ada Writer"
    assert first.description == "First key passage 1. … Second passage 1."
    assert first.keywords == ["agentic ai"]
    assert first.published_at == datetime(2026, 10, 12, 8, tzinfo=UTC)


async def test_several_markets_and_no_keywords():
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"results": [{"url": "https://x.example"}]})  # no title

    items, _ = await collect(handler, keywords=["healthcare"], markets=["USA", "UK"])
    [body] = bodies
    assert body["query"] == "latest news about healthcare"
    assert "userLocation" not in body
    assert items == []

    # Without anything to search, no request is made (never a generic topic).
    with pytest.raises(SourceError) as exc:
        await collect(handler, markets=["USA"])
    assert exc.value.kind == SourceErrorKind.NOT_CONFIGURED
    assert len(bodies) == 1


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, SourceErrorKind.AUTH), (429, SourceErrorKind.RATE_LIMITED)],
)
async def test_errors_stop_the_run(status, kind):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json={"error": "nope"})

    with pytest.raises(SourceError) as err:
        await collect(handler, ["a", "b", "c"])
    assert err.value.kind == kind
    assert len(calls) == 1  # no point repeating a request that will fail the same way


async def test_missing_key_is_not_configured():
    with pytest.raises(SourceError) as err:
        await collect(lambda r: httpx.Response(200), settings=Settings(_env_file=None))
    assert err.value.kind == SourceErrorKind.NOT_CONFIGURED


def test_window_matches_discovery_since():
    body = exa.search_body("ai", (datetime.now(UTC) - timedelta(hours=1)).isoformat(), None)
    assert set(body) == {"query", "type", "contents", "startPublishedDate"}
