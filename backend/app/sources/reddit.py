import asyncio
from datetime import UTC, datetime

from app.core.config import Settings
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

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_API = "https://oauth.reddit.com"
PUBLIC = "https://www.reddit.com"
# Unauthenticated access is heavily rate limited: keep requests few and spaced.
PUBLIC_MAX_REQUESTS = 4
PUBLIC_DELAY_SECONDS = 1.5


class RedditSource(TrendSource):
    key = "reddit"
    name = "Reddit"
    description = "Hot posts from your subreddits and top posts mentioning your keywords."
    pricing = "free_tier"
    docs_url = "https://www.reddit.com/prefs/apps"
    env_vars = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET")

    def _has_oauth(self, settings: Settings) -> bool:
        return bool(settings.reddit_client_id and settings.reddit_client_secret)

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        if self._has_oauth(settings):
            return Configuration(configured=True, mode="OAuth API (scores and comments)")
        return Configuration(
            configured=True,
            mode="Public RSS (limited: no scores, strict rate limits)",
            note=(
                "Add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET from a free “script” app at "
                "reddit.com/prefs/apps for vote counts and reliable access."
            ),
        )

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        subreddits = [s.strip().removeprefix("r/") for s in ctx.inputs.subreddits if s.strip()]
        subreddits = subreddits[:8] or ["popular"]
        keywords = ctx.inputs.keywords[:5]
        if self._has_oauth(ctx.settings):
            return await self._collect_oauth(ctx, subreddits, keywords)
        return await self._collect_public(ctx, subreddits, keywords)

    # -- OAuth API -------------------------------------------------------------
    async def _token(self, ctx: SourceContext) -> str:
        resp = await self.request(
            ctx,
            "POST",
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(ctx.settings.reddit_client_id or "", ctx.settings.reddit_client_secret or ""),
            headers={"User-Agent": ctx.settings.trend_user_agent},
        )
        token = resp.json().get("access_token")
        if not token:
            raise SourceError(SourceErrorKind.AUTH, "Reddit did not return an access token.")
        return token

    async def _collect_oauth(
        self, ctx: SourceContext, subreddits: list[str], keywords: list[str]
    ) -> list[RawTrendItem]:
        headers = {
            "Authorization": f"bearer {await self._token(ctx)}",
            "User-Agent": ctx.settings.trend_user_agent,
        }
        jobs = [
            self._listing(ctx, f"{OAUTH_API}/r/{sub}/hot", {"limit": "25"}, headers)
            for sub in subreddits
        ]
        jobs += [
            self._listing(
                ctx,
                f"{OAUTH_API}/search",
                {"q": kw, "sort": "top", "t": "day", "limit": "15"},
                headers,
                keyword=kw,
            )
            for kw in keywords
        ]
        return await self.gather_partial(ctx, jobs)

    async def _listing(
        self,
        ctx: SourceContext,
        url: str,
        params: dict[str, str],
        headers: dict[str, str],
        keyword: str | None = None,
    ) -> list[RawTrendItem]:
        data = await self.get_json(ctx, url, params=params, headers=headers)
        items: list[RawTrendItem] = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            if post.get("over_18") or post.get("stickied") or not post.get("title"):
                continue
            score = int(post.get("score") or 0)
            comments = int(post.get("num_comments") or 0)
            created = post.get("created_utc")
            items.append(
                RawTrendItem(
                    source=self.key,
                    source_item_id=str(post.get("id")),
                    title=post["title"],
                    description=(post.get("selftext") or "")[:500] or None,
                    keywords=[keyword.lower()] if keyword else [],
                    category=f"r/{post.get('subreddit')}" if post.get("subreddit") else None,
                    source_url=f"https://www.reddit.com{post.get('permalink', '')}",
                    author=post.get("author"),
                    published_at=datetime.fromtimestamp(created, UTC) if created else None,
                    engagement=score,
                    engagement_label=f"{score:,} upvotes · {comments:,} comments",
                    raw_data={"comments": comments, "link": post.get("url")},
                )
            )
        return items

    # -- Public RSS fallback ---------------------------------------------------
    async def _collect_public(
        self, ctx: SourceContext, subreddits: list[str], keywords: list[str]
    ) -> list[RawTrendItem]:
        requests = [(f"{PUBLIC}/r/{sub}/hot/.rss", {"limit": "25"}, None) for sub in subreddits]
        requests += [
            (f"{PUBLIC}/search.rss", {"q": kw, "sort": "top", "t": "day", "limit": "15"}, kw)
            for kw in keywords
        ]
        requests = requests[:PUBLIC_MAX_REQUESTS]
        items: list[RawTrendItem] = []
        errors: list[SourceError] = []
        for index, (url, params, keyword) in enumerate(requests):
            if index:
                await asyncio.sleep(PUBLIC_DELAY_SECONDS)
            try:
                resp = await self.request(
                    ctx,
                    "GET",
                    url,
                    params=params,
                    headers={"User-Agent": ctx.settings.trend_user_agent},
                )
            except SourceError as exc:
                errors.append(exc)
                if exc.kind == SourceErrorKind.RATE_LIMITED:
                    break  # further requests would be refused too
                continue
            for entry in await asyncio.to_thread(parse_feed, resp.content):
                if entry.published and entry.published < ctx.since:
                    continue
                items.append(
                    RawTrendItem(
                        source=self.key,
                        source_item_id=entry.id.removeprefix("t3_"),
                        title=entry.title,
                        keywords=[keyword.lower()] if keyword else [],
                        category=entry.categories[0] if entry.categories else None,
                        source_url=entry.link,
                        author=entry.author,
                        published_at=entry.published,
                    )
                )
        if errors and not items:
            raise errors[0]
        if errors:
            ctx.warn(self.name, f"some requests failed: {errors[0].message}")
        return items
