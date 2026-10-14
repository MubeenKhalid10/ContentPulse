"""Google Trends, Technology only, through trendspy.

trendspy reads the same "Trending now" data as trends.google.com, including
Google's own topic labels, so the list can be cut to the Technology topic. It
is an unofficial client: Google can rate-limit or change it at any time, so
every failure maps to a SourceError and never stops the other sources.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from app.core.config import Settings
from app.sources.base import (
    Configuration,
    RawTrendItem,
    SourceContext,
    SourceError,
    SourceErrorKind,
    SourceInputs,
    TrendSource,
    compact_number,
)
from app.sources.locations import country_codes

# Google's topic id for "Technology" (trendspy.constants.TREND_TOPICS).
TECHNOLOGY_TOPIC = 18
MAX_MARKETS = 5
# trendspy is blocking (requests); give each market this long in a thread.
MARKET_TIMEOUT = 45.0
MARKET_GAP = 1.0


def fetch_tech_trends(geo: str, hours: int = 24) -> list[dict[str, Any]]:
    """Technology searches trending now in one market (blocking; run in a thread)."""
    from trendspy import Trends  # imported lazily: heavy (pandas) and optional

    trends = Trends(request_delay=1.0, max_retries=1)
    results = trends.trending_now(geo=geo, hours=hours).filter_by_topic(TECHNOLOGY_TOPIC)
    out = []
    for k in results:
        started = k.started_timestamp[0] if k.started_timestamp else None
        out.append(
            {
                "keyword": k.keyword,
                "volume": k.volume,
                "growth_pct": k.volume_growth_pct,
                "started": started,
                "related": list(k.trend_keywords or [])[:10],
                "topics": list(k.topic_names or []),
            }
        )
    return out


def _error(exc: Exception) -> SourceError:
    name = type(exc).__name__
    text = str(exc).lower()
    if "quota" in name.lower() or "429" in text or "too many" in text:
        return SourceError(SourceErrorKind.RATE_LIMITED, "Google Trends is rate limiting requests.")
    return SourceError(SourceErrorKind.UNAVAILABLE, f"Google Trends request failed ({name}).")


class GoogleTrendsTechSource(TrendSource):
    key = "google_trends_tech"
    name = "Google Trends · Technology"
    description = (
        "Technology searches rising right now in each target market, with search volume "
        "and growth, from Google's “Trending now” data (via trendspy)."
    )
    pricing = "free"
    docs_url = "https://github.com/sdil87/trendspy"

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        try:
            import trendspy  # noqa: F401
        except ImportError:
            return Configuration(
                False, None, (), note="Install the trendspy package on the server."
            )
        return Configuration(True, "Trending now, Technology topic (no key needed)")

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        geos = country_codes(ctx.inputs.locations)[:MAX_MARKETS]
        # One market at a time: trendspy waits between its own requests too.
        return await self.sequential_partial(
            ctx,
            [self._market(ctx, geo) for geo in geos],
            delay=MARKET_GAP,
            stop_on=frozenset({SourceErrorKind.RATE_LIMITED}),
        )

    async def _market(self, ctx: SourceContext, geo: str) -> list[RawTrendItem]:
        async def fetch() -> list[dict[str, Any]]:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(fetch_tech_trends, geo), timeout=MARKET_TIMEOUT
                )
            except TimeoutError as exc:
                raise SourceError(
                    SourceErrorKind.UNAVAILABLE, "Google Trends took too long."
                ) from exc
            except SourceError:
                raise
            except Exception as exc:  # trendspy/requests raise their own types
                raise _error(exc) from exc

        # The same market's list is shared by every organization targeting it.
        rows = await self.cached_json(ctx, self.key, {"geo": geo, "hours": "24"}, fetch)
        items = []
        for row in rows:
            keyword = str(row.get("keyword") or "").strip()
            if not keyword:
                continue
            started = row.get("started")
            published = (
                datetime.fromtimestamp(started, UTC) if isinstance(started, int | float) else None
            )
            day = published.date().isoformat() if published else "undated"
            volume = row.get("volume") if isinstance(row.get("volume"), int) else None
            items.append(
                RawTrendItem(
                    source=self.key,
                    source_item_id=f"{geo}:{keyword.lower()}:{day}"[:500],
                    title=keyword,
                    topic=keyword,
                    keywords=[k.lower() for k in row.get("related") or [keyword]][:10],
                    category="Technology",
                    location=geo,
                    source_url=(
                        "https://trends.google.com/trends/explore"
                        f"?q={quote(keyword)}&geo={geo}&date=now%201-d"
                    ),
                    published_at=published,
                    engagement=volume,
                    engagement_label=f"{compact_number(volume)}+ searches" if volume else None,
                    raw_data={
                        "volume_growth_pct": row.get("growth_pct"),
                        "topics": row.get("topics"),
                    },
                )
            )
        return items
