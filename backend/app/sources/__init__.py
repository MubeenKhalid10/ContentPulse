"""Registry of trend source adapters (spec §10)."""

from app.core.config import Settings
from app.sources.additional_news import (
    ApiTubeNewsSource,
    NewsDataSource,
    SerpApiNewsSource,
    TheNewsApiSource,
    WorldNewsSource,
)
from app.sources.base import SourceInputs, TrendSource
from app.sources.exa import ExaSource
from app.sources.google_news import GoogleNewsSource
from app.sources.google_trends import GoogleTrendsSource
from app.sources.google_trends_tech import GoogleTrendsTechSource
from app.sources.hacker_news import HackerNewsSource
from app.sources.instagram import InstagramSource
from app.sources.linkedin import LinkedInSource
from app.sources.news_apis import GNewsSource, NewsApiSource
from app.sources.reddit import RedditSource
from app.sources.rss import RssSource
from app.sources.x import XSource

SOURCES: dict[str, TrendSource] = {
    source.key: source
    for source in (
        GoogleTrendsSource(),
        GoogleTrendsTechSource(),
        GoogleNewsSource(),
        HackerNewsSource(),
        RedditSource(),
        RssSource(),
        NewsApiSource(),
        GNewsSource(),
        WorldNewsSource(),
        NewsDataSource(),
        TheNewsApiSource(),
        ExaSource(),
        SerpApiNewsSource(),
        ApiTubeNewsSource(),
        XSource(),
        InstagramSource(),
        LinkedInSource(),
    )
}

# Stand-in organization inputs for judging server readiness: a new organization
# has no keywords or feeds yet, and those are its own to add later.
_FILLED_INPUTS = SourceInputs(
    locations=[], keywords=["placeholder"], rss_feeds=["https://example.com/feed"]
)


def default_sources(settings: Settings) -> list[str]:
    """Sources switched on for a new organization (admins can change them).

    Every source that doesn't need server setup: keyless feeds, plus keyed APIs
    whose keys are present. Sources still waiting for the organization's own
    keywords or feeds are on too, and run once those are added.
    """
    return [
        key
        for key, source in SOURCES.items()
        if source.pricing != "unavailable"
        and source.configuration(settings, _FILLED_INPUTS).configured
    ]


# Sources that need no API key or token (they read public feeds). Calling them
# costs nothing, so "Discover New Trends" may run them on every click.
KEYLESS_SOURCES = frozenset(
    key
    for key, source in SOURCES.items()
    if not source.env_vars and source.pricing != "unavailable"
)


def get_source(key: str) -> TrendSource | None:
    return SOURCES.get(key)
