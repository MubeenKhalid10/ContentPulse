import asyncio

from app.core.config import Settings
from app.sources.base import (
    Configuration,
    RawTrendItem,
    SourceContext,
    SourceInputs,
    TrendSource,
)
from app.sources.feeds import parse_feed
from app.sources.locations import GLOBAL_LOCATION, Location

BASE = "https://news.google.com/rss"
MAX_PER_FEED = 25


def _edition(location: Location) -> dict[str, str]:
    loc = location if not location.is_global else Location("US", "United States")
    cc, lang = loc.code, loc.language
    return {"hl": f"{lang}-{cc}" if lang == "en" else lang, "gl": cc, "ceid": f"{cc}:{lang}"}


class GoogleNewsSource(TrendSource):
    key = "google_news"
    name = "Google News"
    description = "Top stories per market plus recent coverage of your tracked keywords."
    pricing = "free"
    docs_url = "https://news.google.com"

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        return Configuration(configured=True, mode="Public RSS feeds (no key needed)")

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        locations = ctx.inputs.locations[:5] or [GLOBAL_LOCATION]
        jobs = [self._feed(ctx, BASE, _edition(loc), loc, keyword=None) for loc in locations]
        # Keyword searches in the primary market only, to keep request volume low.
        primary = locations[0]
        for keyword in ctx.inputs.keywords[:6]:
            params = {"q": f'"{keyword}" when:2d', **_edition(primary)}
            jobs.append(self._feed(ctx, f"{BASE}/search", params, primary, keyword=keyword))
        return await self.gather_partial(ctx, jobs)

    async def _feed(
        self,
        ctx: SourceContext,
        url: str,
        params: dict[str, str],
        location: Location,
        keyword: str | None,
    ) -> list[RawTrendItem]:
        resp = await self.request(ctx, "GET", url, params=params)
        entries = await asyncio.to_thread(parse_feed, resp.content)
        items: list[RawTrendItem] = []
        for entry in entries[:MAX_PER_FEED]:
            if entry.published and entry.published < ctx.since:
                continue
            title = entry.title
            # Google News titles end with " - Publisher".
            if entry.source and title.endswith(f" - {entry.source}"):
                title = title[: -len(entry.source) - 3]
            items.append(
                RawTrendItem(
                    source=self.key,
                    source_item_id=entry.id,
                    title=title,
                    keywords=[keyword.lower()] if keyword else [],
                    category=None if keyword else "top_stories",
                    location=location.code,
                    source_url=entry.link,
                    author=entry.source,
                    published_at=entry.published,
                    raw_data={"publisher": entry.source, "matched_keyword": keyword},
                )
            )
        return items
