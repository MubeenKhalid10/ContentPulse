"""Optional news providers with API-key based access."""

from app.core.config import Settings
from app.sources.base import (
    Configuration,
    RawTrendItem,
    SourceContext,
    SourceError,
    SourceErrorKind,
    SourceInputs,
    TrendSource,
    missing_settings,
)
from app.sources.feeds import parse_date
from app.sources.locations import country_codes


def _query(inputs: SourceInputs) -> str:
    return " OR ".join(inputs.keywords[:6]) or "technology"


def _news_item(
    source: str,
    article: dict,
    *,
    title_key: str = "title",
    url_key: str = "url",
    description_key: str = "description",
    published_key: str = "publishedAt",
    author_key: str = "source",
) -> RawTrendItem | None:
    title = article.get(title_key) or article.get("name")
    url = article.get(url_key) or article.get("link")
    if not title or not url:
        return None
    author = article.get(author_key)
    if isinstance(author, dict):
        author = author.get("name")
    return RawTrendItem(
        source=source,
        source_item_id=str(article.get("id") or url)[:500],
        title=str(title)[:1000],
        description=article.get(description_key) or article.get("snippet"),
        location="GLOBAL",
        source_url=str(url),
        author=str(author)[:300] if author else None,
        published_at=parse_date(article.get(published_key) or article.get("published_at")),
        raw_data=article,
    )


class WorldNewsSource(TrendSource):
    key = "world_news"
    name = "World News API"
    description = "Global news search with broad language, country, and date filters."
    pricing = "free_tier"
    docs_url = "https://worldnewsapi.com/docs/"
    env_vars = ("WORLD_NEWS_API_KEY",)

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        missing = missing_settings(settings, "world_news_api_key")
        return Configuration(not missing, "REST API" if not missing else None, missing)

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        key = ctx.settings.world_news_api_key
        if not key:
            raise SourceError(SourceErrorKind.NOT_CONFIGURED, "WORLD_NEWS_API_KEY is not set.")
        data = await self.get_json(
            ctx,
            "https://api.worldnewsapi.com/search-news",
            params={
                "text": _query(ctx.inputs),
                "language": "en",
                "earliest-publish-date": ctx.since.strftime("%Y-%m-%d %H:%M:%S"),
                "number": "50",
            },
            headers={"x-api-key": key},
        )
        return [item for article in data.get("news", []) if (item := _news_item(self.key, article))]


class NewsDataSource(TrendSource):
    key = "newsdata"
    name = "NewsData.io"
    description = "Recent global news searchable by tracked keywords and markets."
    pricing = "free_tier"
    docs_url = "https://newsdata.io/documentation"
    env_vars = ("NEWSDATA_API_KEY",)

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        missing = missing_settings(settings, "newsdata_api_key")
        return Configuration(not missing, "REST API" if not missing else None, missing)

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        key = ctx.settings.newsdata_api_key
        if not key:
            raise SourceError(SourceErrorKind.NOT_CONFIGURED, "NEWSDATA_API_KEY is not set.")
        params = {"apikey": key, "q": _query(ctx.inputs), "language": "en"}
        countries = country_codes(ctx.inputs.locations)
        if countries:
            params["country"] = ",".join(c.lower() for c in countries[:5])
        data = await self.get_json(ctx, "https://newsdata.io/api/1/latest", params=params)
        return [
            item
            for article in data.get("results", [])
            if (
                item := _news_item(
                    self.key,
                    article,
                    url_key="link",
                    description_key="description",
                    published_key="pubDate",
                    author_key="creator",
                )
            )
        ]


class SerpApiNewsSource(TrendSource):
    key = "serpapi_news"
    name = "SerpApi Google News"
    description = "Structured Google News search results for tracked keywords."
    pricing = "paid"
    docs_url = "https://serpapi.com/google-news-api"
    env_vars = ("SERP_API_KEY",)

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        missing = missing_settings(settings, "serp_api_key")
        return Configuration(not missing, "REST API" if not missing else None, missing)

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        key = ctx.settings.serp_api_key
        if not key:
            raise SourceError(SourceErrorKind.NOT_CONFIGURED, "SERP_API_KEY is not set.")
        data = await self.get_json(
            ctx,
            "https://serpapi.com/search.json",
            params={"engine": "google_news", "q": _query(ctx.inputs), "api_key": key, "hl": "en"},
        )
        return [
            item
            for article in data.get("news_results", [])
            if (
                item := _news_item(
                    self.key,
                    article,
                    url_key="link",
                    description_key="snippet",
                    published_key="date",
                    author_key="source",
                )
            )
        ]


class ApiTubeNewsSource(TrendSource):
    key = "apitube_news"
    name = "APITube News"
    description = "Real-time news search with publisher and topic metadata."
    pricing = "paid"
    docs_url = "https://apitube.io/"
    env_vars = ("APITUBE_NEWS_API_KEY",)

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        missing = missing_settings(settings, "apitube_news_api_key")
        return Configuration(not missing, "REST API" if not missing else None, missing)

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        key = ctx.settings.apitube_news_api_key
        if not key:
            raise SourceError(SourceErrorKind.NOT_CONFIGURED, "APITUBE_NEWS_API_KEY is not set.")
        data = await self.get_json(
            ctx,
            "https://api.apitube.io/v1/news/everything",
            params={"query": _query(ctx.inputs), "language": "en", "limit": "50"},
            headers={"x-api-key": key},
        )
        articles = data.get("articles") or data.get("data") or data.get("results") or []
        return [
            item
            for article in articles
            if (
                item := _news_item(
                    self.key,
                    article,
                    url_key="href",
                    description_key="description",
                    published_key="published_at",
                    author_key="author",
                )
            )
        ]
