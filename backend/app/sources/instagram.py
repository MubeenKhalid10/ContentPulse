"""Instagram hashtag trends through the Instagram API with Facebook Login.

Hashtag search (`ig_hashtag_search`, `{hashtag-id}/top_media`) exists only on
the Facebook Login path (graph.facebook.com). It needs:

- a Facebook-issued token (User or Page access token, starts with "EAA") with
  `instagram_basic`, plus `pages_show_list` / `pages_read_engagement` so the
  Page that owns the Instagram account is reachable;
- the Instagram professional account's IG user ID (INSTAGRAM_BUSINESS_ACCOUNT_ID),
  linked to a Facebook Page the token's user can access;
- the app's "Instagram Public Content Access" feature.

Tokens from "Instagram API with Instagram Login" (start with "IGAA"/"IGQ") work
only on graph.instagram.com, which has no hashtag search; graph.facebook.com
rejects them with code 190 "Cannot parse access token". They are detected up
front instead of being reported as "expired".

The token is sent in the Authorization header, never in the URL, and Meta's
error messages are scrubbed of anything token-like before they are shown.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.core.config import Settings
from app.sources import quota
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
    token_cache,
)
from app.sources.feeds import parse_date

GRAPH_HOST = "https://graph.facebook.com"
MAX_HASHTAGS_PER_RUN = 5
HASHTAG_GAP = 0.5
STOP_ON = frozenset({SourceErrorKind.AUTH, SourceErrorKind.RATE_LIMITED})

TokenKind = Literal["facebook", "instagram_login", "unknown"]

INSTAGRAM_LOGIN_TOKEN = (
    "INSTAGRAM_ACCESS_TOKEN is an Instagram Login token (starts with IGAA/IGQ). Hashtag "
    "search only exists on the Instagram API with Facebook Login: generate a Facebook User "
    "or Page access token (starts with EAA) for the Page linked to your Instagram "
    "professional account, with instagram_basic, pages_show_list and pages_read_engagement."
)
EXPIRED = (
    "The Instagram (Facebook) access token has expired. Generate a new long-lived token, "
    "update INSTAGRAM_ACCESS_TOKEN and restart the API."
)
REVOKED = (
    "The Instagram (Facebook) access token was revoked (password change, logout, or the app "
    "was removed from the account). Generate a new token, update INSTAGRAM_ACCESS_TOKEN "
    "and restart the API."
)
INVALID = (
    "Meta rejected INSTAGRAM_ACCESS_TOKEN as invalid. Check that the whole token was copied "
    "and that it is a Facebook User or Page access token (starts with EAA)."
)
NO_PUBLIC_CONTENT = (
    "Hashtag search needs the 'Instagram Public Content Access' feature on your Meta app. "
    "Request it under App Review (Advanced Access) in the Meta developer dashboard; a new "
    "token will not fix this."
)
MISSING_PERMISSION = (
    "The token is missing a permission Instagram needs. Grant instagram_basic, "
    "pages_show_list and pages_read_engagement when generating the token, then update "
    "INSTAGRAM_ACCESS_TOKEN."
)
BAD_ACCOUNT = (
    "INSTAGRAM_BUSINESS_ACCOUNT_ID was not found or this token cannot access it. Use the "
    "Instagram professional account's IG user ID (usually starts with 1784…) from the "
    "Facebook Page's instagram_business_account, and make sure the token's user manages "
    "that Page."
)
HASHTAG_LIMIT = (
    "Instagram allows 30 unique hashtags per 7 days per account; that limit is reached. "
    "It resets on a rolling 7-day window."
)

_TOKEN_LIKE = re.compile(r"\b(EAA|IGAA|IGQ)[A-Za-z0-9_\-]{8,}")
# Graph API subcodes for code 190 (access token problems).
_EXPIRED_SUBCODES = {463}
_REVOKED_SUBCODES = {458, 459, 460, 464, 467, 492, 452}
_RATE_LIMIT_CODES = {4, 17, 32, 341, 368, 613, 80002, 80006}


def hashtag_for(keyword: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", keyword.lower())


def token_kind(token: str | None) -> TokenKind:
    token = (token or "").strip()
    if token.startswith(("IGAA", "IGQ")):
        return "instagram_login"
    if token.startswith("EAA"):
        return "facebook"
    return "unknown"


def scrub(text: str, token: str | None = None) -> str:
    """Remove the token (and anything token-shaped) from text shown to people."""
    if token:
        text = text.replace(token, "***")
    return _TOKEN_LIKE.sub("***", text)


@dataclass(frozen=True)
class MetaError:
    status: int
    code: int | None
    subcode: int | None
    type: str | None
    message: str

    @classmethod
    def from_response(cls, resp: httpx.Response, token: str | None) -> "MetaError":
        try:
            body = resp.json()
        except ValueError:
            body = {}
        err = body.get("error") if isinstance(body, dict) else None
        err = err if isinstance(err, dict) else {}
        message = str(err.get("error_user_msg") or err.get("message") or resp.reason_phrase)
        return cls(
            status=resp.status_code,
            code=_int(err.get("code")),
            subcode=_int(err.get("error_subcode")),
            type=err.get("type"),
            message=scrub(message, token)[:300],
        )

    def describe(self) -> str:
        parts = [f"HTTP {self.status}"]
        if self.code is not None:
            parts.append(f"code {self.code}")
        if self.subcode is not None:
            parts.append(f"subcode {self.subcode}")
        return f"{', '.join(parts)}: {self.message}"


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def explain(err: MetaError) -> SourceError:
    """Turn Meta's error into an actionable SourceError (spec: never a generic 'auth')."""
    code, sub, text = err.code, err.subcode, err.message.lower()
    detail = f" (Meta: {err.describe()})"
    if code == 190 or code == 102:
        if sub in _EXPIRED_SUBCODES or "expired" in text:
            return SourceError(SourceErrorKind.AUTH, EXPIRED + detail)
        if sub in _REVOKED_SUBCODES:
            return SourceError(SourceErrorKind.AUTH, REVOKED + detail)
        if "cannot parse" in text:
            return SourceError(SourceErrorKind.AUTH, INVALID + detail)
        return SourceError(SourceErrorKind.AUTH, INVALID + detail)
    if "public content access" in text:
        return SourceError(SourceErrorKind.AUTH, NO_PUBLIC_CONTENT + detail)
    if code == 10 or (code is not None and 200 <= code <= 299):
        return SourceError(SourceErrorKind.AUTH, MISSING_PERMISSION + detail)
    if code == 24 or ("hashtag" in text and "limit" in text):
        return SourceError(SourceErrorKind.RATE_LIMITED, HASHTAG_LIMIT + detail)
    if code in _RATE_LIMIT_CODES or err.status == 429:
        return SourceError(SourceErrorKind.RATE_LIMITED, "Meta is rate limiting requests." + detail)
    if code == 100 and (sub == 33 or "user_id" in text or "does not exist" in text):
        return SourceError(SourceErrorKind.AUTH, BAD_ACCOUNT + detail)
    if err.status >= 500 or code in (1, 2):
        return SourceError(SourceErrorKind.UNAVAILABLE, "Meta's Graph API is unavailable." + detail)
    return SourceError(SourceErrorKind.BAD_RESPONSE, "Meta rejected the request." + detail)


async def graph_get(
    client: httpx.AsyncClient, settings: Settings, path: str, params: dict[str, str] | None = None
) -> dict:
    """GET on the Graph API with the token in the header and Meta errors explained."""
    token = settings.instagram_access_token or ""
    url = f"{GRAPH_HOST}/{settings.instagram_graph_version}/{path}"
    try:
        resp = await client.get(
            url, params=params or {}, headers={"Authorization": f"Bearer {token}"}
        )
    except httpx.TimeoutException as exc:
        raise SourceError(SourceErrorKind.UNAVAILABLE, "Meta's Graph API timed out.") from exc
    except httpx.HTTPError as exc:
        # The exception text can include the URL; only its type is reported.
        raise SourceError(
            SourceErrorKind.UNAVAILABLE, f"Connection to Meta failed ({type(exc).__name__})."
        ) from None
    if resp.status_code >= 400:
        raise explain(MetaError.from_response(resp, token))
    try:
        data = resp.json()
    except ValueError as exc:
        raise SourceError(SourceErrorKind.BAD_RESPONSE, "Meta returned invalid JSON.") from exc
    return data if isinstance(data, dict) else {}


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
            "Needs the Instagram API with Facebook Login (a Facebook token for the Page linked "
            "to your Instagram professional account) and the Instagram Public Content Access "
            "feature. Instagram allows 30 unique hashtags per 7 days."
        )
        if missing:
            return Configuration(configured=False, missing=missing, note=note)
        if token_kind(settings.instagram_access_token) == "instagram_login":
            return Configuration(configured=False, note=INSTAGRAM_LOGIN_TOKEN)
        if not inputs.keywords:
            return Configuration(configured=False, note="Add keywords to track in Settings.")
        return Configuration(configured=True, mode="Graph API hashtag search", note=note)

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        s = ctx.settings
        if not (s.instagram_access_token and s.instagram_business_account_id):
            raise SourceError(SourceErrorKind.NOT_CONFIGURED, "Instagram credentials are not set.")
        if token_kind(s.instagram_access_token) == "instagram_login":
            raise SourceError(SourceErrorKind.AUTH, INSTAGRAM_LOGIN_TOKEN)
        tags = list(dict.fromkeys(t for t in (hashtag_for(k) for k in ctx.inputs.keywords) if t))
        if not tags:
            ctx.warn(self.name, "no keywords to turn into hashtags.")
            return []
        # One hashtag at a time: an auth or limit error stops the rest (and spares
        # the 30-hashtags-per-week budget).
        jobs = [self._hashtag(ctx, tag) for tag in tags[:MAX_HASHTAGS_PER_RUN]]
        return await self.sequential_partial(ctx, jobs, delay=HASHTAG_GAP, stop_on=STOP_ON)

    async def _graph(self, ctx: SourceContext, path: str, params: dict[str, str]) -> dict:
        user_id = ctx.settings.instagram_business_account_id or ""
        query = {**params, "user_id": user_id}
        # Shared (in memory only) so organizations tracking the same hashtag
        # spend one lookup; the token travels in a header, never in the key.
        name = "instagram.hashtag_search" if path == "ig_hashtag_search" else "instagram.top_media"
        credential = token_cache.fingerprint("instagram", ctx.settings.instagram_access_token)

        async def produce() -> dict:
            if path == "ig_hashtag_search":
                # Only real searches (not cache hits) use one of the account's
                # 30 unique hashtags per 7 days.
                await quota.reserve_hashtag(user_id, params.get("q", ""))
            return await graph_get(ctx.client, ctx.settings, path, query)

        return await self.cached_json(
            ctx, name, {"path": path, **query, "credential": credential}, produce
        )

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
