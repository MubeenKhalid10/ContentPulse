from datetime import UTC, datetime, timedelta
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
from app.sources.feeds import parse_date

API = "https://api.x.com"


class XSource(TrendSource):
    """Conversation volume on X for each tracked keyword (recent search, last 7 days max)."""

    key = "x"
    name = "X (Twitter)"
    description = "How much people are posting about your tracked keywords, and how they engage."
    pricing = "paid"
    docs_url = "https://developer.x.com/en/docs/x-api/tweets/search/introduction"
    env_vars = ("X_BEARER_TOKEN", "X_API_KEY", "X_API_SECRET")

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        note = (
            "Recent search needs a paid X API plan (Basic or higher). Uses your tracked keywords."
        )
        if settings.x_bearer_token:
            mode = "API v2 (bearer token)"
        elif settings.x_api_key and settings.x_api_secret:
            mode = "API v2 (app key + secret)"
        else:
            return Configuration(
                configured=False,
                missing=("X_BEARER_TOKEN",),
                note=f"Set X_BEARER_TOKEN, or X_API_KEY and X_API_SECRET. {note}",
            )
        if not inputs.keywords:
            return Configuration(configured=False, note="Add keywords to track in Settings.")
        return Configuration(configured=True, mode=mode, note=note)

    async def _bearer(self, ctx: SourceContext) -> str:
        if ctx.settings.x_bearer_token:
            return ctx.settings.x_bearer_token
        if not (ctx.settings.x_api_key and ctx.settings.x_api_secret):
            raise SourceError(SourceErrorKind.NOT_CONFIGURED, "X credentials are not set.")
        resp = await self.request(
            ctx,
            "POST",
            f"{API}/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(ctx.settings.x_api_key, ctx.settings.x_api_secret),
        )
        token = resp.json().get("access_token")
        if not token:
            raise SourceError(SourceErrorKind.AUTH, "X did not return a bearer token.")
        return token

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        if not ctx.inputs.keywords:
            ctx.warn(self.name, "no keywords to track; nothing to search.")
            return []
        headers = {"Authorization": f"Bearer {await self._bearer(ctx)}"}
        # Recent search covers at most the last 7 days.
        start = max(ctx.since, datetime.now(UTC) - timedelta(days=6, hours=23))
        jobs = [self._keyword(ctx, kw, headers, start) for kw in ctx.inputs.keywords[:5]]
        return await self.gather_partial(ctx, jobs)

    async def _keyword(
        self, ctx: SourceContext, keyword: str, headers: dict[str, str], start: datetime
    ) -> list[RawTrendItem]:
        data = await self.get_json(
            ctx,
            f"{API}/2/tweets/search/recent",
            headers=headers,
            params={
                "query": f'"{keyword}" -is:retweet -is:reply lang:en',
                "max_results": "50",
                "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tweet.fields": "public_metrics,created_at",
            },
        )
        posts = data.get("data") or []
        if not posts:
            return []

        def interactions(post: dict) -> int:
            m = post.get("public_metrics") or {}
            return sum(
                int(m.get(k) or 0)
                for k in ("like_count", "retweet_count", "reply_count", "quote_count")
            )

        total = sum(interactions(p) for p in posts)
        top = max(posts, key=interactions)
        latest = max(
            (parse_date(p.get("created_at")) for p in posts if p.get("created_at")), default=None
        )
        day = (latest or datetime.now(UTC)).date().isoformat()
        return [
            RawTrendItem(
                source=self.key,
                source_item_id=f"{keyword.lower()}:{day}",
                title=f"{keyword}: {len(posts)} recent posts on X",
                topic=keyword,
                description=(top.get("text") or "")[:280] or None,
                keywords=[keyword.lower()],
                source_url=f"https://x.com/search?q={quote(keyword)}&f=live",
                published_at=latest,
                engagement=total,
                engagement_label=f"{len(posts)} posts · {compact_number(total)} interactions",
                raw_data={"post_count": len(posts), "top_post_id": top.get("id")},
            )
        ]
