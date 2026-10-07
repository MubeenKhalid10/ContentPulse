import re
from datetime import UTC, datetime

from app.core.config import Settings
from app.sources.base import (
    Configuration,
    RawTrendItem,
    SourceContext,
    SourceInputs,
    TrendSource,
)

API = "https://hn.algolia.com/api/v1"
HN_PREFIX = re.compile(r"^(Ask|Show|Tell|Launch) HN:\s*", re.I)


class HackerNewsSource(TrendSource):
    key = "hacker_news"
    name = "Hacker News"
    description = "Front-page and keyword-matching stories from the tech community, with votes."
    pricing = "free"
    docs_url = "https://hn.algolia.com/api"

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        return Configuration(configured=True, mode="Algolia search API (no key needed)")

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        # Rounded down to the hour so concurrent runs (other organizations, a
        # retry a few seconds later) share the cached response.
        since = int(ctx.since.timestamp()) // 3600 * 3600
        jobs = [self._search(ctx, "search", {"tags": "front_page", "hitsPerPage": "30"})]
        for keyword in ctx.inputs.keywords[:6]:
            jobs.append(
                self._search(
                    ctx,
                    "search",
                    {
                        "query": keyword,
                        "tags": "story",
                        "numericFilters": f"created_at_i>{since},points>5",
                        "hitsPerPage": "15",
                    },
                    keyword=keyword,
                )
            )
        return await self.gather_partial(ctx, jobs)

    async def _search(
        self, ctx: SourceContext, endpoint: str, params: dict[str, str], keyword: str | None = None
    ) -> list[RawTrendItem]:
        data = await self.get_json(ctx, f"{API}/{endpoint}", params=params)
        items: list[RawTrendItem] = []
        for hit in data.get("hits", []):
            title = HN_PREFIX.sub("", hit.get("title") or "").strip()
            if not title:
                continue
            points = int(hit.get("points") or 0)
            comments = int(hit.get("num_comments") or 0)
            hn_url = f"https://news.ycombinator.com/item?id={hit['objectID']}"
            created = hit.get("created_at_i")
            items.append(
                RawTrendItem(
                    source=self.key,
                    source_item_id=str(hit["objectID"]),
                    title=title,
                    keywords=[keyword.lower()] if keyword else [],
                    category="technology",
                    source_url=hit.get("url") or hn_url,
                    author=hit.get("author"),
                    published_at=datetime.fromtimestamp(created, UTC) if created else None,
                    engagement=points,
                    engagement_label=f"{points:,} points · {comments:,} comments",
                    raw_data={"discussion_url": hn_url, "comments": comments},
                )
            )
        return items
