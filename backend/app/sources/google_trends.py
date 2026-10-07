import asyncio
import re
from urllib.parse import quote

from app.core.config import Settings
from app.sources.base import (
    Configuration,
    RawTrendItem,
    SourceContext,
    SourceInputs,
    TrendSource,
)
from app.sources.feeds import parse_feed
from app.sources.locations import country_codes

FEED_URL = "https://trends.google.com/trending/rss"


def parse_traffic(value: str | None) -> int | None:
    """'200K+' -> 200000, '1M+' -> 1000000, '2,000+' -> 2000."""
    if not value:
        return None
    match = re.match(r"([\d.,]+)\s*([KMB]?)", value.strip(), re.I)
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    scale = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[match.group(2).upper()]
    return int(number * scale)


class GoogleTrendsSource(TrendSource):
    key = "google_trends"
    name = "Google Trends"
    description = (
        "Searches rising right now in each target market, from Google's public “Trending now” feed."
    )
    pricing = "free"
    docs_url = "https://trends.google.com/trending"

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        return Configuration(configured=True, mode="Trending now RSS feed (no key needed)")

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        geos = country_codes(ctx.inputs.locations)
        if all(loc.is_global for loc in ctx.inputs.locations):
            ctx.warn(self.name, "no worldwide feed exists; using United States.")
        return await self.gather_partial(ctx, [self._geo(ctx, geo) for geo in geos[:10]])

    async def _geo(self, ctx: SourceContext, geo: str) -> list[RawTrendItem]:
        resp = await self.request(ctx, "GET", FEED_URL, params={"geo": geo})
        entries = await asyncio.to_thread(parse_feed, resp.content)
        items: list[RawTrendItem] = []
        for entry in entries:
            el = entry.element
            traffic_text = el.find("ht:approx_traffic") if el else None
            traffic_raw = traffic_text.get_text(strip=True) if traffic_text else None
            news = []
            for news_item in el.find_all("ht:news_item") if el else []:
                title = news_item.find("ht:news_item_title")
                url = news_item.find("ht:news_item_url")
                source = news_item.find("ht:news_item_source")
                news.append(
                    {
                        "title": title.get_text(strip=True) if title else None,
                        "url": url.get_text(strip=True) if url else None,
                        "source": source.get_text(strip=True) if source else None,
                    }
                )
            query = entry.title
            day = entry.published.date().isoformat() if entry.published else "undated"
            items.append(
                RawTrendItem(
                    source=self.key,
                    source_item_id=f"{geo}:{query.lower()}:{day}",
                    title=query,
                    topic=query,
                    description=news[0]["title"] if news and news[0]["title"] else None,
                    keywords=[query.lower()],
                    location=geo,
                    source_url=(
                        f"https://trends.google.com/trends/explore?q={quote(query)}"
                        f"&geo={geo}&date=now%201-d"
                    ),
                    published_at=entry.published,
                    engagement=parse_traffic(traffic_raw),
                    engagement_label=f"{traffic_raw} searches" if traffic_raw else None,
                    raw_data={"approx_traffic": traffic_raw, "news": news[:5]},
                )
            )
        return items
