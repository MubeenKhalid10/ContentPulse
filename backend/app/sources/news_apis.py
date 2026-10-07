"""Keyed news APIs: NewsAPI.org and GNews. Both are optional upgrades over the
free Google News feeds (more metadata, descriptions, category filters)."""

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

GNEWS_REQUEST_GAP = 1.2


def _keyword_query(keywords: list[str]) -> str:
    return " OR ".join(f'"{k}"' for k in keywords)


class NewsApiSource(TrendSource):
    key = "newsapi"
    name = "NewsAPI"
    description = "Headlines and articles from 80,000+ publishers, searchable by keyword."
    pricing = "free_tier"
    docs_url = "https://newsapi.org/docs"
    env_vars = ("NEWS_API_KEY",)

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        missing = missing_settings(settings, "news_api_key")
        return Configuration(
            configured=not missing,
            mode="REST API" if not missing else None,
            missing=missing,
            note="The free Developer plan is for development only; production needs a paid plan.",
        )

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        if not ctx.settings.news_api_key:
            raise SourceError(SourceErrorKind.NOT_CONFIGURED, "NEWS_API_KEY is not set.")
        headers = {"X-Api-Key": ctx.settings.news_api_key}
        jobs = [
            self._fetch(
                ctx, "top-headlines", {"country": cc.lower(), "pageSize": "30"}, headers, cc
            )
            for cc in country_codes(ctx.inputs.locations)[:3]
        ]
        if ctx.inputs.keywords:
            params = {
                "q": _keyword_query(ctx.inputs.keywords[:6]),
                "from": ctx.since.isoformat(timespec="seconds"),
                "sortBy": "popularity",
                "language": "en",
                "pageSize": "30",
            }
            jobs.append(self._fetch(ctx, "everything", params, headers, None))
        return await self.gather_partial(ctx, jobs)

    async def _fetch(
        self,
        ctx: SourceContext,
        endpoint: str,
        params: dict[str, str],
        headers: dict[str, str],
        country: str | None,
    ) -> list[RawTrendItem]:
        data = await self.get_json(
            ctx, f"https://newsapi.org/v2/{endpoint}", params=params, headers=headers
        )
        if data.get("status") == "error":
            raise SourceError(SourceErrorKind.BAD_RESPONSE, data.get("message", "NewsAPI error"))
        items = []
        for article in data.get("articles", []):
            title = article.get("title")
            if not title or title == "[Removed]" or not article.get("url"):
                continue
            items.append(
                RawTrendItem(
                    source=self.key,
                    source_item_id=article["url"][:500],
                    title=title,
                    description=article.get("description"),
                    location=country or "GLOBAL",
                    source_url=article["url"],
                    author=(article.get("source") or {}).get("name"),
                    published_at=parse_date(article.get("publishedAt")),
                    raw_data={"author": article.get("author")},
                )
            )
        return items


class GNewsSource(TrendSource):
    key = "gnews"
    name = "GNews"
    description = "Top headlines by country and keyword search across global news sources."
    pricing = "free_tier"
    docs_url = "https://gnews.io/docs/v4"
    env_vars = ("GNEWS_API_KEY",)

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        missing = missing_settings(settings, "gnews_api_key")
        return Configuration(
            configured=not missing,
            mode="REST API" if not missing else None,
            missing=missing,
            note="Free plan: 100 requests per day.",
        )

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        if not ctx.settings.gnews_api_key:
            raise SourceError(SourceErrorKind.NOT_CONFIGURED, "GNEWS_API_KEY is not set.")
        key = ctx.settings.gnews_api_key
        jobs = []
        for location in ctx.inputs.locations[:3]:
            cc = "us" if location.is_global else location.code.lower()
            params = {
                "category": "general",
                "lang": location.language,
                "country": cc,
                "max": "10",
                "apikey": key,
            }
            jobs.append(self._fetch(ctx, "top-headlines", params, location.code))
        if ctx.inputs.keywords:
            params = {
                "q": " OR ".join(ctx.inputs.keywords[:5]),
                "lang": "en",
                "max": "10",
                "from": ctx.since.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "apikey": key,
            }
            jobs.append(self._fetch(ctx, "search", params, "GLOBAL"))
        # The free plan allows about one request per second.
        return await self.sequential_partial(ctx, jobs, delay=GNEWS_REQUEST_GAP)

    async def _fetch(
        self, ctx: SourceContext, endpoint: str, params: dict[str, str], location: str
    ) -> list[RawTrendItem]:
        data = await self.get_json(ctx, f"https://gnews.io/api/v4/{endpoint}", params=params)
        if "errors" in data:
            raise SourceError(SourceErrorKind.BAD_RESPONSE, str(data["errors"])[:200])
        items = []
        for article in data.get("articles", []):
            if not article.get("title") or not article.get("url"):
                continue
            items.append(
                RawTrendItem(
                    source=self.key,
                    source_item_id=article["url"][:500],
                    title=article["title"],
                    description=article.get("description"),
                    location=location,
                    source_url=article["url"],
                    author=(article.get("source") or {}).get("name"),
                    published_at=parse_date(article.get("publishedAt")),
                )
            )
        return items
