"""Optional news providers with API-key based access."""

from dataclasses import dataclass, field

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

QUERY_JOINER = " OR "
# Keywords considered per run (the first ones are the organization's priorities).
MAX_QUERY_KEYWORDS = 6
# Most requests one source makes per run: each costs free-tier quota.
MAX_QUERIES_PER_RUN = 3
FALLBACK_QUERY = "technology"

# Provider limits on the search text (characters, including " OR ").
NEWSDATA_QUERY_LIMIT = 100  # newsdata.io: HTTP 422 "Query cannot exceed 100 characters"
WORLD_NEWS_TEXT_LIMIT = 100  # worldnewsapi.com: HTTP 400 on a longer `text`
# Gap between one source's consecutive requests (per-second provider limits).
NEWSDATA_REQUEST_GAP = 1.0
WORLD_NEWS_REQUEST_GAP = 1.0
# Errors that end a source's run early: further requests would fail the same way.
STOP_ON = frozenset({SourceErrorKind.AUTH, SourceErrorKind.RATE_LIMITED})


def _query(inputs: SourceInputs) -> str:
    return " OR ".join(inputs.keywords[:6]) or "technology"


@dataclass
class QueryPlan:
    """Keyword searches that each fit a provider's length limit."""

    queries: list[str]
    # Keywords longer than the limit, searched by their leading whole words.
    shortened: list[str] = field(default_factory=list)
    # Keywords left out: no whole word fits, or beyond MAX_QUERIES_PER_RUN.
    dropped: list[str] = field(default_factory=list)


def _clean_keywords(keywords: list[str]) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for raw in keywords:
        term = " ".join(str(raw).split())
        if term and term.casefold() not in seen:
            seen.add(term.casefold())
            terms.append(term)
    return terms


def _whole_words(term: str, limit: int) -> str:
    """The longest run of leading whole words that fits (never cuts a word)."""
    kept: list[str] = []
    for word in term.split():
        if len(" ".join([*kept, word])) > limit:
            break
        kept.append(word)
    return " ".join(kept)


def plan_queries(
    keywords: list[str],
    max_chars: int,
    *,
    max_keywords: int = MAX_QUERY_KEYWORDS,
    max_queries: int = MAX_QUERIES_PER_RUN,
) -> QueryPlan:
    """Pack keywords into as few `a OR b OR c` searches as fit within `max_chars`.

    Keywords are never split mid-word, and earlier (higher-priority) keywords
    land in earlier searches; a single keyword longer than the limit is searched
    by its leading whole words.
    """
    plan = QueryPlan(queries=[])
    batches: list[list[str]] = []
    for term in _clean_keywords(keywords)[:max_keywords]:
        if len(term) > max_chars:
            short = _whole_words(term, max_chars)
            if not short:
                plan.dropped.append(term)
                continue
            plan.shortened.append(term)
            term = short
        # First fit: the earliest search with room, so fewer requests are needed
        # and higher-priority keywords stay in the earlier searches.
        for batch in batches:
            if len(QUERY_JOINER.join([*batch, term])) <= max_chars:
                batch.append(term)
                break
        else:
            batches.append([term])
    for batch in batches[max_queries:]:
        plan.dropped.extend(batch)
    plan.queries = [QUERY_JOINER.join(batch) for batch in batches[:max_queries]]
    return plan


def _report(ctx: SourceContext, source: str, plan: QueryPlan, limit: int) -> None:
    if plan.shortened:
        ctx.warn(
            source,
            f"shortened keywords over {limit} characters to whole words: "
            + ", ".join(plan.shortened),
        )
    if plan.dropped:
        ctx.warn(source, "skipped keywords this run: " + ", ".join(plan.dropped))


def _dedupe(items: list[RawTrendItem]) -> list[RawTrendItem]:
    """Articles found by more than one search appear once (first one wins)."""
    seen: set[str] = set()
    unique: list[RawTrendItem] = []
    for item in items:
        keys = {item.source_item_id}
        if item.source_url:
            keys.add(item.source_url.strip().rstrip("/").casefold())
        if keys & seen:
            continue
        seen |= keys
        unique.append(item)
    return unique


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
        plan = plan_queries(ctx.inputs.keywords, WORLD_NEWS_TEXT_LIMIT)
        _report(ctx, self.name, plan, WORLD_NEWS_TEXT_LIMIT)
        # `text` is optional: with no keywords, search by date and language only.
        texts: list[str | None] = [*plan.queries] or [None]
        jobs = [self._search(ctx, key, text) for text in texts]
        items = await self.sequential_partial(
            ctx, jobs, delay=WORLD_NEWS_REQUEST_GAP, stop_on=STOP_ON
        )
        return _dedupe(items)

    async def _search(self, ctx: SourceContext, key: str, text: str | None) -> list[RawTrendItem]:
        params = {
            "language": "en",
            "earliest-publish-date": ctx.since.strftime("%Y-%m-%d %H:%M:%S"),
            "number": "50",
        }
        if text:
            params["text"] = text
        data = await self.get_json(
            ctx,
            "https://api.worldnewsapi.com/search-news",
            params=params,
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
        plan = plan_queries(ctx.inputs.keywords, NEWSDATA_QUERY_LIMIT)
        _report(ctx, self.name, plan, NEWSDATA_QUERY_LIMIT)
        countries = country_codes(ctx.inputs.locations)
        country = ",".join(c.lower() for c in countries[:5]) if countries else None
        queries = plan.queries or [FALLBACK_QUERY]
        jobs = [self._search(ctx, key, query, country) for query in queries]
        items = await self.sequential_partial(
            ctx, jobs, delay=NEWSDATA_REQUEST_GAP, stop_on=STOP_ON
        )
        return _dedupe(items)

    async def _search(
        self, ctx: SourceContext, key: str, query: str, country: str | None
    ) -> list[RawTrendItem]:
        params = {"apikey": key, "q": query, "language": "en"}
        if country:
            params["country"] = country
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
