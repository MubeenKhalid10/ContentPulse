"""Which provider requests may be shared between organizations, for how long,
and how their cache keys are built.

A cache key identifies *what was asked*, never *who asked*: it is a SHA-256 of
the provider, endpoint and the parameters that change the result. Secrets (API
keys, tokens, Authorization headers) are never part of it, and request headers
are never used. Each policy lists the parameters it understands; a request with
any other parameter is not shared at all, so two semantically different
requests can never be merged by accident.

TTLs are engineering defaults (override per policy with PROVIDER_CACHE_TTLS);
whether a provider's terms allow keeping its responses is a separate question,
answered by `persist` and PROVIDER_CACHE_PERSIST_SOURCES.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit, urlunsplit

KEY_VERSION = "v1"
MINUTE, HOUR, DAY = 60, 3600, 86400


@dataclass(frozen=True)
class CachePolicy:
    ttl: int  # seconds a response is reused
    # Query parameters (or JSON body fields for POST) that change the result.
    params: frozenset[str]
    # Parameters that carry credentials: dropped from the key, never stored.
    secret_params: frozenset[str] = frozenset()
    # Times (ISO 8601, "YYYY-MM-DD HH:MM:SS" or epoch seconds) floored to a
    # bucket of `ttl`, so runs minutes apart share one response.
    time_params: frozenset[str] = frozenset()
    # Comma-separated sets whose order doesn't matter (countries, locales).
    set_params: frozenset[str] = frozenset()
    # Free-text searches the provider treats case-insensitively.
    casefold_params: frozenset[str] = frozenset()
    # POST requests with a JSON body (search APIs that only take POST).
    post_body: bool = False
    # "opt_in": persisted in the shared Postgres cache only when listed in
    # PROVIDER_CACHE_PERSIST_SOURCES (after checking the provider's terms).
    # "never": the provider's terms require honoring deletions of user
    # content, which a shared cache can't propagate; memory-only, short TTL.
    persist: Literal["opt_in", "never"] = "opt_in"
    note: str = ""


_NEWS_TIME = frozenset({"from", "published_after", "earliest-publish-date"})

POLICIES: dict[str, CachePolicy] = {
    "google_trends": CachePolicy(45 * MINUTE, frozenset({"geo"})),
    "google_trends_tech": CachePolicy(HOUR, frozenset({"geo", "hours"})),
    "google_news": CachePolicy(
        45 * MINUTE, frozenset({"hl", "gl", "ceid", "q"}), casefold_params=frozenset({"q"})
    ),
    "hacker_news": CachePolicy(
        20 * MINUTE,
        frozenset({"tags", "query", "numericFilters", "hitsPerPage"}),
        casefold_params=frozenset({"query"}),
    ),
    "reddit": CachePolicy(
        20 * MINUTE,
        frozenset({"limit", "q", "sort", "t"}),
        casefold_params=frozenset({"q"}),
        persist="never",
        note="Reddit Data API terms: deleted content must be removed from stored copies.",
    ),
    "newsapi": CachePolicy(
        2 * HOUR,
        frozenset({"country", "pageSize", "q", "from", "sortBy", "language"}),
        time_params=frozenset({"from"}),
        note="NewsAPI's free Developer plan does not allow production use at all.",
    ),
    "gnews": CachePolicy(
        2 * HOUR,
        frozenset({"category", "lang", "country", "max", "q", "from"}),
        secret_params=frozenset({"apikey"}),
        time_params=frozenset({"from"}),
    ),
    "world_news": CachePolicy(
        2 * HOUR,
        frozenset({"language", "earliest-publish-date", "number", "text"}),
        time_params=_NEWS_TIME,
        casefold_params=frozenset({"text"}),
    ),
    "newsdata": CachePolicy(
        2 * HOUR,
        frozenset({"q", "language", "country"}),
        secret_params=frozenset({"apikey"}),
        set_params=frozenset({"country"}),
    ),
    "the_news_api": CachePolicy(
        2 * HOUR,
        frozenset({"search", "language", "published_after", "sort", "limit", "locale"}),
        secret_params=frozenset({"api_token"}),
        time_params=_NEWS_TIME,
        set_params=frozenset({"locale"}),
    ),
    "serpapi_news": CachePolicy(
        2 * HOUR, frozenset({"engine", "q", "hl"}), secret_params=frozenset({"api_key"})
    ),
    "apitube_news": CachePolicy(2 * HOUR, frozenset({"query", "language", "limit"})),
    "exa": CachePolicy(
        12 * HOUR,
        frozenset(
            {"query", "type", "contents", "numResults", "startPublishedDate", "userLocation"}
        ),
        time_params=frozenset({"startPublishedDate"}),
        post_body=True,
    ),
    "x": CachePolicy(
        HOUR,
        frozenset({"query", "max_results", "start_time", "tweet.fields"}),
        time_params=frozenset({"start_time"}),
        persist="never",
        note="X Developer Agreement: deleted posts must be removed from stored copies.",
    ),
    # Instagram: hashtag ids are stable; top media changes daily. Meta's terms
    # limit storing platform data and require deletions to be honored.
    # `credential` is a one-way fingerprint of the access token (never the
    # token): a rotated token gets fresh responses at once.
    "instagram.hashtag_search": CachePolicy(
        30 * DAY,
        frozenset({"path", "q", "user_id", "credential"}),
        casefold_params=frozenset({"q"}),
        persist="never",
        note="Meta Platform Terms: limits on storing data; deletions must be honored.",
    ),
    "instagram.top_media": CachePolicy(
        DAY,
        frozenset({"path", "fields", "limit", "user_id", "credential"}),
        persist="never",
        note="Meta Platform Terms: limits on storing data; deletions must be honored.",
    ),
}
# Parameter names that are always credentials, whatever the provider.
ALWAYS_SECRET = frozenset(
    {"apikey", "api_key", "api_token", "access_token", "token", "key", "client_secret"}
)


def source_of(name: str) -> str:
    """Policy name -> source key ("instagram.top_media" -> "instagram")."""
    return name.split(".", 1)[0]


@dataclass
class KeyParts:
    """The canonical request, for tests and debugging (never stored)."""

    name: str
    method: str
    url: str
    params: list[tuple[str, str]] = field(default_factory=list)
    body: Any = None


def _floor_time(value: Any, bucket: int) -> str | None:
    if isinstance(value, int | float) or (isinstance(value, str) and value.isdigit()):
        seconds = int(value)
    else:
        text = str(value).strip().replace("Z", "+00:00").replace(" ", "T", 1)
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        seconds = int(moment.timestamp())
    floored = seconds - seconds % max(bucket, 1)
    return datetime.fromtimestamp(floored, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize(name: str, value: Any, policy: CachePolicy, ttl: int) -> Any:
    if name in policy.time_params:
        return _floor_time(value, ttl)
    if isinstance(value, dict):
        return {k: _normalize(k, v, policy, ttl) for k, v in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_normalize(name, v, policy, ttl) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, int | float):
        return value
    text = " ".join(str(value).split())
    if name in policy.set_params:
        text = ",".join(sorted({part.strip().lower() for part in text.split(",") if part.strip()}))
    if name in policy.casefold_params:
        text = text.casefold()
    return text


def canonical_request(
    name: str,
    policy: CachePolicy,
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    *,
    ttl: int | None = None,
) -> KeyParts | None:
    """The request as the cache sees it, or None when it must not be shared
    (an unknown parameter, an unparsable time, a POST without a body policy)."""
    ttl = ttl or policy.ttl
    method = method.upper()
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    merged = {**query, **(params or {})}
    base = urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, "", ""))
    secrets = policy.secret_params | ALWAYS_SECRET
    canonical: list[tuple[str, str]] = []
    for key, value in merged.items():
        if key in secrets:
            continue
        if key not in policy.params:
            return None
        normalized = _normalize(key, value, policy, ttl)
        if normalized is None:
            return None
        canonical.append((key, str(normalized)))
    canonical.sort()

    canonical_body = None
    if method == "POST":
        if not policy.post_body or not isinstance(body, dict):
            return None
        fields = {k: v for k, v in body.items() if k not in secrets}
        if set(fields) - policy.params:
            return None
        canonical_body = _normalize("", fields, policy, ttl)
        if any(canonical_body.get(k) is None for k in fields if k in policy.time_params):
            return None
    elif method != "GET" or body is not None:
        return None
    return KeyParts(name, method, base, canonical, canonical_body)


def cache_key(parts: KeyParts) -> str:
    material = json.dumps(
        [KEY_VERSION, parts.name, parts.method, parts.url, parts.params, parts.body],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode()).hexdigest()
