import re

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
    missing_settings,
)
from app.sources.feeds import parse_date


def hashtag_for(keyword: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", keyword.lower())


class InstagramSource(TrendSource):
    """Top media for hashtags built from tracked keywords (Instagram Graph API)."""

    key = "instagram"
    name = "Instagram"
    description = "Engagement on top posts for hashtags based on your tracked keywords."
    pricing = "free_tier"
    docs_url = "https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-hashtag-search"
    env_vars = ("INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_BUSINESS_ACCOUNT_ID")

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        missing = missing_settings(
            settings, "instagram_access_token", "instagram_business_account_id"
        )
        note = (
            "Needs an Instagram professional account linked to a Meta app. "
            "Instagram allows 30 unique hashtags per 7 days."
        )
        if missing:
            return Configuration(configured=False, missing=missing, note=note)
        if not inputs.keywords:
            return Configuration(configured=False, note="Add keywords to track in Settings.")
        return Configuration(configured=True, mode="Graph API hashtag search", note=note)

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        s = ctx.settings
        if not (s.instagram_access_token and s.instagram_business_account_id):
            raise SourceError(SourceErrorKind.NOT_CONFIGURED, "Instagram credentials are not set.")
        tags = list(dict.fromkeys(t for t in (hashtag_for(k) for k in ctx.inputs.keywords) if t))
        if not tags:
            ctx.warn(self.name, "no keywords to turn into hashtags.")
            return []
        return await self.gather_partial(ctx, [self._hashtag(ctx, tag) for tag in tags[:5]])

    async def _graph(self, ctx: SourceContext, path: str, params: dict[str, str]) -> dict:
        s = ctx.settings
        params = {
            **params,
            "user_id": s.instagram_business_account_id or "",
            "access_token": s.instagram_access_token or "",
        }
        url = f"https://graph.facebook.com/{s.instagram_graph_version}/{path}"
        try:
            return await self.get_json(ctx, url, params=params)
        except SourceError as exc:
            # The Graph API reports bad/expired tokens as HTTP 400 OAuthException.
            if exc.kind == SourceErrorKind.BAD_RESPONSE and "OAuthException" in exc.message:
                raise SourceError(
                    SourceErrorKind.AUTH, "Instagram access token is invalid or expired."
                ) from exc
            raise

    async def _hashtag(self, ctx: SourceContext, tag: str) -> list[RawTrendItem]:
        found = await self._graph(ctx, "ig_hashtag_search", {"q": tag})
        if not found.get("data"):
            return []
        hashtag_id = found["data"][0]["id"]
        media = await self._graph(
            ctx,
            f"{hashtag_id}/top_media",
            {"fields": "id,caption,like_count,comments_count,permalink,timestamp", "limit": "25"},
        )
        posts = media.get("data") or []
        if not posts:
            return []
        engagement = sum(
            int(p.get("like_count") or 0) + int(p.get("comments_count") or 0) for p in posts
        )
        latest = max(
            (parse_date(p.get("timestamp")) for p in posts if p.get("timestamp")), default=None
        )
        top = max(posts, key=lambda p: int(p.get("like_count") or 0))
        day = latest.date().isoformat() if latest else "undated"
        return [
            RawTrendItem(
                source=self.key,
                source_item_id=f"{tag}:{day}",
                title=f"#{tag} on Instagram",
                topic=f"#{tag}",
                description=(top.get("caption") or "")[:280] or None,
                keywords=[tag],
                source_url=f"https://www.instagram.com/explore/tags/{tag}/",
                published_at=latest,
                engagement=engagement,
                engagement_label=f"{compact_number(engagement)} likes + comments on top posts",
                raw_data={"top_post": top.get("permalink"), "posts": len(posts)},
            )
        ]
