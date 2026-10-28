"""Trend source adapter interface (spec §10, §11).

Every source converts its data into `RawTrendItem` (the normalized trend
model). Sources are optional by design: `configuration()` reports whether the
keys a source needs are present, and discovery simply skips sources that are
not configured. A source failing (bad key, rate limit, outage) is recorded in
its health and never stops other sources or the application.
"""

import asyncio
import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal

import httpx

from app.core.config import Settings
from app.services.knowledge.fetcher import Resolver, system_resolver
from app.sources.locations import Location

GLOBAL = "GLOBAL"
Pricing = Literal["free", "free_tier", "paid", "unavailable"]


@dataclass
class RawTrendItem:
    """Normalized observation from any source (spec §11)."""

    source: str
    source_item_id: str
    title: str
    # Set when the source itself names the topic (a search query, a hashtag).
    topic: str | None = None
    description: str | None = None
    keywords: list[str] = field(default_factory=list)
    category: str | None = None
    location: str = GLOBAL  # ISO 3166-1 alpha-2, or GLOBAL
    source_url: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    engagement: int | None = None
    engagement_label: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


class SourceErrorKind(StrEnum):
    NOT_CONFIGURED = "not_configured"
    AUTH = "auth"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    BAD_RESPONSE = "bad_response"
    # Not failures: the request was deliberately not sent (app/sources/quota.py).
    BUDGET_EXHAUSTED = "budget_exhausted"
    COOLING_DOWN = "cooling_down"


# Kinds that mean "skipped on purpose", reported as such rather than as errors.
SKIPPED_KINDS = frozenset({SourceErrorKind.BUDGET_EXHAUSTED, SourceErrorKind.COOLING_DOWN})


class SourceError(Exception):
    def __init__(
        self,
        kind: SourceErrorKind,
        message: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status
        # Seconds the provider asked us to wait (Retry-After), if it said.
        self.retry_after = retry_after

    @property
    def public_message(self) -> str:
        """Fixed wording safe for platform-wide health, which every organization
        sees. `message` can hold one organization's feed URL or query (via the
        provider's error body), so it only goes into that organization's run."""
        text = PUBLIC_ERRORS.get(self.kind, PUBLIC_ERRORS[SourceErrorKind.UNAVAILABLE])
        return f"{text} (HTTP {self.status})" if self.status else text


PUBLIC_ERRORS = {
    SourceErrorKind.NOT_CONFIGURED: "Not configured.",
    SourceErrorKind.AUTH: "Access denied by the provider. Check the API key or credentials.",
    SourceErrorKind.RATE_LIMITED: "Rate limited or usage limit reached at the provider.",
    SourceErrorKind.UNAVAILABLE: "The provider was unavailable or did not respond in time.",
    SourceErrorKind.BAD_RESPONSE: "The provider rejected a request or sent an unexpected response.",
    SourceErrorKind.BUDGET_EXHAUSTED: "Skipped: the daily request budget is used up.",
    SourceErrorKind.COOLING_DOWN: "Skipped: paused after the provider's rate limit.",
}
_PUBLIC_ERROR = re.compile(
    "^(" + "|".join(re.escape(t) for t in PUBLIC_ERRORS.values()) + r")( \(HTTP \d{3}\))?$"
)


def is_public_error(text: str | None) -> bool:
    """True for health text produced by `SourceError.public_message`."""
    return bool(text) and _PUBLIC_ERROR.match(text) is not None


@dataclass(frozen=True)
class Configuration:
    configured: bool
    # How the source will run, e.g. "OAuth API" vs "public RSS (limited)".
    mode: str | None = None
    missing: tuple[str, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class SourceInputs:
    """Per-organization inputs that shape what sources collect."""

    locations: list[Location]
    keywords: list[str]
    subreddits: list[str] = field(default_factory=list)
    rss_feeds: list[str] = field(default_factory=list)
    # The organization's content language: used where a market doesn't set one.
    language: str = "en"


@dataclass
class SourceContext:
    client: httpx.AsyncClient
    settings: Settings
    inputs: SourceInputs
    since: datetime
    warnings: list[str] = field(default_factory=list)
    # DNS resolver for the SSRF guard on user-supplied URLs (tests inject one).
    resolver: Resolver = system_resolver
    # Whose run this is: only for per-organization request budgets.
    organization_id: str | None = None

    def warn(self, source: str, message: str) -> None:
        self.warnings.append(f"{source}: {message}")


class TrendSource(ABC):
    key: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    pricing: ClassVar[Pricing]
    docs_url: ClassVar[str | None] = None
    # Settings (env vars) this source can use, shown in the UI.
    env_vars: ClassVar[tuple[str, ...]] = ()
    # Collects from organization-owned inputs (e.g. its own feed URLs): its
    # health says nothing about the provider and is never recorded platform-wide.
    org_private: ClassVar[bool] = False

    @abstractmethod
    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        """Whether this source can run. Must never raise or make requests."""

    @abstractmethod
    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        """Fetch and normalize items. Raise SourceError on total failure."""

    # -- helpers ---------------------------------------------------------------
    async def request(
        self,
        ctx: SourceContext,
        method: str,
        url: str,
        *,
        cache: str | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """HTTP call with errors mapped to SourceError kinds.

        Requests covered by a cache policy (`cache`, default: this source's
        key) are shared between organizations through the provider cache, keyed
        by what was asked and never by credentials (app/sources/cache_policy.py).
        Credential exchanges (`auth=`) are never cached.
        """
        if "auth" not in kwargs:
            from app.sources import provider_cache

            name = cache or self.key
            prepared = provider_cache.prepare(
                name, method, url, kwargs.get("params"), kwargs.get("json")
            )
            send = self._guarded(
                ctx, name, lambda: self._send(ctx, method, url, **kwargs), prepared
            )
            if prepared is not None:
                return await provider_cache.get_or_fetch(prepared, send)
            if method.upper() == "GET":
                # No policy covers it: share within this process only.
                return await request_cache.get_or_fetch(request_cache.key(url, kwargs), send)
            return await send()
        return await self._guarded(
            ctx, cache or self.key, lambda: self._send(ctx, method, url, **kwargs), None
        )()

    def _guarded(
        self,
        ctx: SourceContext,
        name: str,
        call: Callable[[], Awaitable[httpx.Response]],
        prepared: Any,
    ) -> Callable[[], Awaitable[httpx.Response]]:
        """An outbound request under the provider's cooldown and budget
        (app/sources/quota.py). Runs only on a cache miss."""
        from app.sources import provider_cache, quota

        async def stale() -> httpx.Response | None:
            return await provider_cache.stale_response(prepared) if prepared else None

        return lambda: quota.guard(name, ctx.organization_id, call, stale=stale)

    async def cached_json(
        self,
        ctx: SourceContext,
        name: str,
        params: dict[str, Any],
        produce: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Share a non-HTTP fetch (a client library, a helper that calls the
        API itself) through the provider cache. `params` must describe
        everything that changes the result; `produce` returns JSON data."""
        from app.sources import provider_cache

        url = f"https://provider-cache.invalid/{name}"
        prepared = provider_cache.prepare(name, "GET", url, params)
        if prepared is None:
            from app.sources import quota

            return await quota.guard(name, ctx.organization_id, produce)

        async def call() -> httpx.Response:
            return httpx.Response(
                200, json=await produce(), request=httpx.Request("GET", prepared.url)
            )

        fetch = self._guarded(ctx, name, call, prepared)
        return (await provider_cache.get_or_fetch(prepared, fetch)).json()

    async def _send(
        self,
        ctx: SourceContext,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            resp = await ctx.client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise SourceError(SourceErrorKind.UNAVAILABLE, "Request timed out.") from exc
        except httpx.HTTPError as exc:
            raise SourceError(
                SourceErrorKind.UNAVAILABLE, f"Connection failed ({type(exc).__name__})."
            ) from exc
        status = resp.status_code
        retry_after = None
        if status in (402, 429, 503):
            from app.sources.quota import parse_retry_after

            retry_after = parse_retry_after(resp.headers.get("retry-after"))
        if status in (401, 403):
            raise SourceError(
                SourceErrorKind.AUTH,
                f"Access denied (HTTP {status}). Check the API key or credentials.",
                status=status,
            )
        if status == 429:
            raise SourceError(
                SourceErrorKind.RATE_LIMITED,
                "Rate limited by the provider.",
                status=status,
                retry_after=retry_after,
            )
        if status == 402:
            # Used by several news APIs for "daily/plan usage limit reached".
            raise SourceError(
                SourceErrorKind.RATE_LIMITED,
                "Usage limit reached for this plan (HTTP 402).",
                status=status,
                retry_after=retry_after,
            )
        if status >= 500:
            raise SourceError(
                SourceErrorKind.UNAVAILABLE, f"Provider error (HTTP {status}).", status=status
            )
        if status >= 400:
            raise SourceError(
                SourceErrorKind.BAD_RESPONSE,
                f"Request rejected (HTTP {status}): {resp.text[:200]}",
                status=status,
            )
        return resp

    async def get_json(self, ctx: SourceContext, url: str, **kwargs: Any) -> Any:
        resp = await self.request(ctx, "GET", url, **kwargs)
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceError(SourceErrorKind.BAD_RESPONSE, "Response was not valid JSON.") from exc

    async def gather_partial(
        self,
        ctx: SourceContext,
        jobs: Iterable[Awaitable[list[RawTrendItem]]],
    ) -> list[RawTrendItem]:
        """Run sub-requests; keep partial results, fail only if all of them fail."""
        results = await asyncio.gather(*jobs, return_exceptions=True)
        return self._merge_partial(ctx, results)

    async def sequential_partial(
        self,
        ctx: SourceContext,
        jobs: list[Awaitable[list[RawTrendItem]]],
        delay: float,
        *,
        stop_on: frozenset[SourceErrorKind] = frozenset(),
    ) -> list[RawTrendItem]:
        """Like gather_partial, but one request at a time with a gap."""
        return self._merge_partial(ctx, await run_sequentially(jobs, delay, stop_on=stop_on))

    def _merge_partial(self, ctx: SourceContext, results: list) -> list[RawTrendItem]:
        items: list[RawTrendItem] = []
        errors: list[SourceError] = []
        for result in results:
            if isinstance(result, SourceError):
                errors.append(result)
            elif isinstance(result, BaseException):
                raise result
            else:
                items.extend(result)
        if errors and not items and len(errors) == len(results):
            # Prefer the most actionable error (auth > rate limit > others).
            order = [
                SourceErrorKind.AUTH,
                SourceErrorKind.RATE_LIMITED,
                SourceErrorKind.BUDGET_EXHAUSTED,
                SourceErrorKind.COOLING_DOWN,
            ]
            errors.sort(key=lambda e: order.index(e.kind) if e.kind in order else len(order))
            raise errors[0]
        for error in errors:
            verb = "were skipped" if error.kind in SKIPPED_KINDS else "failed"
            ctx.warn(self.name, f"some requests {verb}: {error.message}")
        return items


REMEMBERED_FAILURES = frozenset({SourceErrorKind.UNAVAILABLE, SourceErrorKind.BAD_RESPONSE})


class RequestCache:
    """Short-lived cache of GET responses shared across discovery runs.

    Concurrent identical requests wait for one in-flight fetch. Transient
    failures are remembered briefly too, so a provider that is down isn't hit
    again by every organization in the same minute.
    """

    SUCCESS_TTL = 600.0
    FAILURE_TTL = 120.0
    MAX_ENTRIES = 2000

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, asyncio.Future]] = {}

    @staticmethod
    def key(url: str, kwargs: dict[str, Any]) -> str:
        params = kwargs.get("params") or {}
        headers = kwargs.get("headers") or {}
        return json.dumps(
            [url, sorted(params.items()), sorted(headers.items())], sort_keys=True, default=str
        )

    def clear(self) -> None:
        self._entries.clear()

    async def get_or_fetch(
        self,
        key: str,
        fetch: Callable[[], Awaitable[httpx.Response]],
        *,
        ttl: float | None = None,
        label: str | None = None,
    ) -> httpx.Response:
        now = time.monotonic()
        entry = self._entries.get(key)
        if entry and entry[0] > now:
            if label:
                from app.sources.provider_cache import cache_stats

                cache_stats.record(label, "memory_hit")
            return await asyncio.shield(entry[1])
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._entries[key] = (now + (ttl or self.SUCCESS_TTL), future)
        self._evict(now)
        try:
            response = await fetch()
        except BaseException as exc:
            # Remember transient failures briefly (an outage, a bad response).
            # Rate limits, exhausted quota and bad credentials are not cache
            # entries: provider cooldowns (app/sources/quota.py) handle those.
            if isinstance(exc, SourceError) and exc.kind in REMEMBERED_FAILURES:
                self._entries[key] = (now + self.FAILURE_TTL, future)
                future.set_exception(exc)
                future.exception()  # mark retrieved: waiters re-raise it
            else:
                self._entries.pop(key, None)
                # Never cancel(): that raises CancelledError in every other
                # organization waiting on this request. Hand them the error
                # (or, if this run itself was cancelled, a retryable one).
                waiter_error = (
                    exc
                    if isinstance(exc, Exception)
                    else SourceError(
                        SourceErrorKind.UNAVAILABLE, "The shared request was interrupted."
                    )
                )
                future.set_exception(waiter_error)
                future.exception()  # mark retrieved: waiters re-raise it
            raise
        future.set_result(response)
        return response

    def _evict(self, now: float) -> None:
        if len(self._entries) <= self.MAX_ENTRIES:
            return
        for k in [k for k, (expiry, _) in self._entries.items() if expiry <= now]:
            del self._entries[k]
        while len(self._entries) > self.MAX_ENTRIES:
            self._entries.pop(next(iter(self._entries)))


request_cache = RequestCache()


class TokenCache:
    """Access tokens from credential exchanges (Reddit, X), reused until shortly
    before they expire. Process memory only: never logged, never persisted."""

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[float, str]] = {}

    @staticmethod
    def fingerprint(*credentials: str | None) -> str:
        import hashlib

        return hashlib.sha256("|".join(c or "" for c in credentials).encode()).hexdigest()

    def get(self, fingerprint: str) -> str | None:
        entry = self._tokens.get(fingerprint)
        if entry and entry[0] > time.monotonic():
            return entry[1]
        self._tokens.pop(fingerprint, None)
        return None

    def put(self, fingerprint: str, token: str, ttl: float) -> None:
        if ttl > 0:
            self._tokens[fingerprint] = (time.monotonic() + ttl, token)

    def clear(self) -> None:
        self._tokens.clear()


token_cache = TokenCache()


async def run_sequentially(
    jobs: list[Awaitable[list["RawTrendItem"]]],
    delay: float,
    *,
    stop_on: frozenset["SourceErrorKind"] = frozenset(),
) -> list[list["RawTrendItem"] | BaseException]:
    """Await sub-requests one at a time (providers with per-second limits).

    An error whose kind is in `stop_on` (e.g. rate limited, bad key) ends the
    run: the remaining requests would fail the same way and only spend quota.
    """
    results: list[list[RawTrendItem] | BaseException] = []
    pending = list(jobs)
    for index, job in enumerate(pending):
        if index:
            await asyncio.sleep(delay)
        try:
            results.append(await job)
        except SourceError as exc:
            results.append(exc)
            if exc.kind in stop_on:
                for skipped in pending[index + 1 :]:
                    close = getattr(skipped, "close", None)
                    if close:
                        close()  # never awaited: release the coroutine quietly
                break
    return results


def search_language(inputs: SourceInputs) -> str:
    """The primary market's language, else the organization's own language."""
    for loc in inputs.locations:
        if loc.code != GLOBAL:
            return loc.language
    return inputs.language or "en"


def missing_settings(settings: Settings, *names: str) -> tuple[str, ...]:
    return tuple(name.upper() for name in names if not getattr(settings, name, None))


def compact_number(value: int) -> str:
    for size, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if value >= size:
            text = f"{value / size:.1f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    return str(value)
