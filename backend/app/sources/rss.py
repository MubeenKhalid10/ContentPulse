import asyncio

from app.core.config import Settings
from app.services.knowledge.fetcher import FetchError, SafeFetcher
from app.sources.base import (
    Configuration,
    RawTrendItem,
    SourceContext,
    SourceError,
    SourceErrorKind,
    SourceInputs,
    TrendSource,
)
from app.sources.feeds import parse_feed

MAX_FEEDS = 20
MAX_PER_FEED = 20


class RssSource(TrendSource):
    key = "rss"
    name = "RSS feeds"
    description = "Industry blogs, trade publications and newsletters you choose (RSS or Atom)."
    pricing = "free"

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        if not inputs.rss_feeds:
            return Configuration(
                configured=False,
                note="Add RSS or Atom feed URLs in Settings → Trend discovery.",
            )
        count = len(inputs.rss_feeds)
        return Configuration(configured=True, mode=f"{count} feed{'s' if count != 1 else ''}")

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        if not ctx.inputs.rss_feeds:
            raise SourceError(SourceErrorKind.NOT_CONFIGURED, "No feeds configured.")
        # Feed URLs come from users: fetch them with the crawler's SSRF guard.
        fetcher = SafeFetcher(ctx.client, ctx.settings, ctx.resolver)
        jobs = [self._feed(ctx, fetcher, url) for url in ctx.inputs.rss_feeds[:MAX_FEEDS]]
        return await self.gather_partial(ctx, jobs)

    async def _feed(self, ctx: SourceContext, fetcher: SafeFetcher, url: str) -> list[RawTrendItem]:
        try:
            result = await fetcher.get(url)
        except FetchError as exc:
            raise SourceError(SourceErrorKind.UNAVAILABLE, f"{url}: {exc.reason}") from exc
        if result.status_code >= 400:
            raise SourceError(SourceErrorKind.UNAVAILABLE, f"{url}: HTTP {result.status_code}")
        entries = await asyncio.to_thread(parse_feed, result.content)
        if not entries:
            raise SourceError(SourceErrorKind.BAD_RESPONSE, f"{url}: not an RSS or Atom feed")
        items: list[RawTrendItem] = []
        for entry in entries[:MAX_PER_FEED]:
            if entry.published and entry.published < ctx.since:
                continue
            items.append(
                RawTrendItem(
                    source=self.key,
                    source_item_id=f"{url}#{entry.id}"[:500],
                    title=entry.title,
                    description=entry.summary,
                    category=entry.categories[0] if entry.categories else None,
                    source_url=entry.link,
                    author=entry.author,
                    published_at=entry.published,
                    raw_data={"feed": url},
                )
            )
        return items
