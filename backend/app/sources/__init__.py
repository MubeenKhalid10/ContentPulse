"""Registry of trend source adapters (spec §10)."""

from app.sources.additional_news import (
    ApiTubeNewsSource,
    NewsDataSource,
    SerpApiNewsSource,
    TheNewsApiSource,
    WorldNewsSource,
)
from app.sources.base import TrendSource
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

# Free sources that need no keys: enabled for new organizations.
DEFAULT_ENABLED_SOURCES = [
    "google_trends",
    "google_news",
    "hacker_news",
    "reddit",
    "rss",
]
# Topic-specific sources, enabled by default only where the industry fits.
TECHNOLOGY_SOURCES = ["google_trends_tech"]


def default_sources(industry: str | None) -> list[str]:
    """Sources switched on for a new organization (admins can change them)."""
    from app.services.trends.industry import is_technology

    extra = TECHNOLOGY_SOURCES if is_technology(industry) else []
    return [*DEFAULT_ENABLED_SOURCES, *extra]


def get_source(key: str) -> TrendSource | None:
    return SOURCES.get(key)
