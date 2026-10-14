"""Exa web search: recent articles for each tracked keyword, with highlights.

Request shape follows Exa's recommended search (query + `type: auto` +
`contents.highlights: true`). The highlights become the article text, which
the writer cites as evidence. Only two extra fields are sent, each for a
product reason: `startPublishedDate` enforces the discovery window every
source shares, and `userLocation` ranks for the organization's market.
"""

from app.core.config import Settings
from app.sources.additional_news import (
    NEEDS_KEYWORDS,
    STOP_ON,
    QueryPlan,
    _clean_keywords,
    _dedupe,
    _report,
)
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

SEARCH_URL = "https://api.exa.ai/search"
# One search per keyword: each is billed, so only the top priorities run.
MAX_SEARCHES_PER_RUN = 3
REQUEST_GAP = 0.5


def search_body(keyword: str, since_iso: str, country: str | None) -> dict:
    body: dict = {
        "query": f"latest news about {keyword}",
        "type": "auto",
        "contents": {"highlights": True},
        "startPublishedDate": since_iso,
    }
    if country:
        body["userLocation"] = country
    return body


class ExaSource(TrendSource):
    key = "exa"
    name = "Exa web search"
    description = (
        "Semantic web search for your tracked keywords: recent articles from across "
        "the web with the key passages already pulled out."
    )
    pricing = "free_tier"
    docs_url = "https://exa.ai/docs/reference/search"
    env_vars = ("EXA_API_KEY",)

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        missing = missing_settings(settings, "exa_api_key")
        if missing:
            return Configuration(False, None, missing)
        if not inputs.keywords:
            return Configuration(False, None, (), note=NEEDS_KEYWORDS)
        return Configuration(True, "Search API")

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        key = ctx.settings.exa_api_key
        if not key:
            raise SourceError(SourceErrorKind.NOT_CONFIGURED, "EXA_API_KEY is not set.")
        keywords = _clean_keywords(ctx.inputs.keywords)
        if not keywords:
            raise SourceError(SourceErrorKind.NOT_CONFIGURED, NEEDS_KEYWORDS)
        searched, skipped = keywords[:MAX_SEARCHES_PER_RUN], keywords[MAX_SEARCHES_PER_RUN:]
        _report(ctx, self.name, QueryPlan(queries=searched, dropped=skipped), 0)
        countries = country_codes(ctx.inputs.locations)
        # A single target market is worth ranking for; several are left to the query.
        country = countries[0] if len(countries) == 1 else None
        since = ctx.since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        jobs = [self._search(ctx, key, search_body(k, since, country), k) for k in searched]
        items = await self.sequential_partial(ctx, jobs, delay=REQUEST_GAP, stop_on=STOP_ON)
        return _dedupe(items)

    async def _search(
        self, ctx: SourceContext, key: str, body: dict, keyword: str
    ) -> list[RawTrendItem]:
        resp = await self.request(ctx, "POST", SEARCH_URL, json=body, headers={"x-api-key": key})
        try:
            data = resp.json()
        except ValueError as exc:
            raise SourceError(SourceErrorKind.BAD_RESPONSE, "Response was not valid JSON.") from exc
        items = []
        for result in data.get("results") or []:
            url, title = result.get("url"), result.get("title")
            if not url or not title:
                continue
            highlights = [h.strip() for h in result.get("highlights") or [] if h and h.strip()]
            items.append(
                RawTrendItem(
                    source=self.key,
                    source_item_id=str(result.get("id") or url)[:500],
                    title=str(title)[:1000],
                    description=" … ".join(highlights)[:2000] or None,
                    keywords=[keyword.lower()],
                    source_url=str(url),
                    author=str(result["author"])[:300] if result.get("author") else None,
                    published_at=parse_date(result.get("publishedDate")),
                    raw_data={
                        "query": body["query"],
                        "highlights": highlights,
                        "image": result.get("image"),
                    },
                )
            )
        return items
