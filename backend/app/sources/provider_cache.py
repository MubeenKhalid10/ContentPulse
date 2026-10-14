"""Shared provider-response cache: process memory first, then Postgres.

Level 1 is `request_cache` (this process; concurrent identical requests wait
for one fetch). Level 2 is the `provider_cache` table, used only with
PROVIDER_CACHE_BACKEND=postgres for providers listed in
PROVIDER_CACHE_PERSIST_SOURCES: it survives restarts and Render sleep and is
shared by every process.

On a level-2 miss one worker claims a short lease and fetches; others poll
briefly for its result, then fetch themselves rather than fail the run. No
database transaction is held open during a provider request, and an abandoned
lease (a killed worker) simply expires and is claimed by the next caller.
Only successful responses are stored; errors never are.
"""

import asyncio
import time
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import logger
from app.sources.cache_policy import (
    POLICIES,
    CachePolicy,
    cache_key,
    canonical_request,
    source_of,
)

POLL_SECONDS = 0.25


class CacheStats:
    """Per-source counters for this process (exported with the metrics)."""

    EVENTS = (
        "memory_hit",
        "db_hit",
        "miss",
        "stored",
        "lease_wait",
        "lease_timeout",
        "stale_served",
        "db_error",
        "uncacheable",
    )

    def __init__(self) -> None:
        self.counts: Counter[tuple[str, str]] = Counter()

    def record(self, source: str, event: str) -> None:
        self.counts[(source_of(source), event)] += 1

    def snapshot(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for (source, event), count in sorted(self.counts.items()):
            out.setdefault(source, {})[event] = count
        return out

    def reset(self) -> None:
        self.counts.clear()


cache_stats = CacheStats()


@dataclass(frozen=True)
class Prepared:
    """A request that may be shared: its policy, effective TTL and key."""

    name: str
    policy: CachePolicy
    ttl: int
    key: str
    method: str
    url: str

    @property
    def source(self) -> str:
        return source_of(self.name)


def effective_ttl(name: str, policy: CachePolicy) -> int:
    overrides = get_settings().provider_cache_ttls
    return int(overrides.get(name, overrides.get(source_of(name), policy.ttl)))


def persists(name: str, policy: CachePolicy) -> bool:
    settings = get_settings()
    return (
        settings.provider_cache_backend == "postgres"
        and policy.persist == "opt_in"
        and source_of(name) in settings.provider_cache_persist_sources
    )


def prepare(
    name: str,
    method: str,
    url: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Prepared | None:
    policy = POLICIES.get(name)
    if policy is None:
        return None
    ttl = effective_ttl(name, policy)
    parts = canonical_request(name, policy, method, url, params, body, ttl=ttl)
    if parts is None:
        cache_stats.record(name, "uncacheable")
        return None
    return Prepared(name, policy, ttl, cache_key(parts), parts.method, parts.url)


# -- level 2: Postgres --------------------------------------------------------


@dataclass
class Row:
    status_code: int | None
    content_type: str | None
    body: bytes | None
    fresh: bool
    stale_ok: bool
    leased: bool

    @property
    def usable(self) -> bool:
        return (
            self.body is not None
            and self.status_code is not None
            and (200 <= self.status_code < 300)
        )


class store:
    """SQL for the provider_cache table. Each call is its own short transaction."""

    @staticmethod
    async def _execute(sql: str, **params: Any):
        from app.db.session import SessionLocal

        async with SessionLocal() as db:
            result = await db.execute(text(sql), params)
            await db.commit()
            return result

    @staticmethod
    async def load(key: str, stale_seconds: float) -> Row | None:
        result = await store._execute(
            """
            SELECT status_code, content_type, body,
                   coalesce(expires_at > now(), false) AS fresh,
                   coalesce(expires_at > now() - make_interval(secs => :stale), false)
                       AS stale_ok,
                   coalesce(lease_until > now(), false) AS leased
            FROM provider_cache WHERE key = :key
            """,
            key=key,
            stale=float(stale_seconds),
        )
        row = result.first()
        return Row(*row) if row else None

    @staticmethod
    async def claim(key: str, source: str, owner: uuid.UUID, seconds: float) -> bool:
        """Take the fetch lease unless the response is fresh or another
        worker's lease is still running."""
        result = await store._execute(
            """
            INSERT INTO provider_cache (key, source, lease_owner, lease_until)
            VALUES (:key, :source, :owner, now() + make_interval(secs => :seconds))
            ON CONFLICT (key) DO UPDATE
              SET lease_owner = excluded.lease_owner, lease_until = excluded.lease_until
              WHERE (provider_cache.lease_until IS NULL OR provider_cache.lease_until <= now())
                AND (provider_cache.body IS NULL OR provider_cache.expires_at IS NULL
                     OR provider_cache.expires_at <= now())
            RETURNING lease_owner
            """,
            key=key,
            source=source,
            owner=owner,
            seconds=float(seconds),
        )
        row = result.first()
        return row is not None and row[0] == owner

    @staticmethod
    async def save(key: str, source: str, response: httpx.Response, ttl: int) -> None:
        await store._execute(
            """
            INSERT INTO provider_cache
              (key, source, status_code, content_type, body, size_bytes,
               fetched_at, expires_at, lease_owner, lease_until)
            VALUES (:key, :source, :status, :content_type, :body, :size,
                    now(), now() + make_interval(secs => :ttl), NULL, NULL)
            ON CONFLICT (key) DO UPDATE SET
              status_code = excluded.status_code, content_type = excluded.content_type,
              body = excluded.body, size_bytes = excluded.size_bytes,
              fetched_at = excluded.fetched_at, expires_at = excluded.expires_at,
              lease_owner = NULL, lease_until = NULL
            """,
            key=key,
            source=source,
            status=response.status_code,
            content_type=(response.headers.get("content-type") or "")[:200] or None,
            body=response.content,
            size=len(response.content),
            ttl=float(ttl),
        )

    @staticmethod
    async def release(key: str, owner: uuid.UUID) -> None:
        await store._execute(
            "DELETE FROM provider_cache WHERE key = :key AND lease_owner = :owner AND body IS NULL",
            key=key,
            owner=owner,
        )
        await store._execute(
            "UPDATE provider_cache SET lease_owner = NULL, lease_until = NULL "
            "WHERE key = :key AND lease_owner = :owner",
            key=key,
            owner=owner,
        )

    @staticmethod
    async def prune(stale_seconds: float, batch: int = 500, max_batches: int = 20) -> int:
        """Delete expired responses (past the stale window) and dead leases, in
        bounded batches so a large backlog never locks the table for long."""
        deleted = 0
        for _ in range(max_batches):
            result = await store._execute(
                """
                DELETE FROM provider_cache WHERE key IN (
                  SELECT key FROM provider_cache
                  WHERE (body IS NOT NULL
                         AND expires_at < now() - make_interval(secs => :stale))
                     OR (body IS NULL
                         AND coalesce(lease_until, created_at) < now() - interval '1 hour')
                  LIMIT :batch
                )
                """,
                stale=float(stale_seconds),
                batch=batch,
            )
            count = result.rowcount or 0
            deleted += count
            if count < batch:
                break
        return deleted

    @staticmethod
    async def purge(source: str | None = None) -> int:
        """Remove stored responses (one provider, or all), e.g. to honor a
        provider's deletion request or after taking it off the persist list."""
        if source is None:
            result = await store._execute("DELETE FROM provider_cache")
        else:
            result = await store._execute(
                "DELETE FROM provider_cache WHERE source = :source", source=source
            )
        return result.rowcount or 0


def _response(prepared: Prepared, row: Row) -> httpx.Response:
    headers = {"content-type": row.content_type} if row.content_type else {}
    return httpx.Response(
        row.status_code or 200,
        content=row.body or b"",
        headers=headers,
        request=httpx.Request(prepared.method, prepared.url),
    )


async def _db_failed(prepared: Prepared, fetch: Callable[[], Awaitable[httpx.Response]]):
    from app.sources.base import SourceError, SourceErrorKind

    cache_stats.record(prepared.name, "db_error")
    logger.warning("Provider cache database unavailable (%s)", prepared.source, exc_info=True)
    if get_settings().provider_cache_on_db_error == "skip":
        raise SourceError(
            SourceErrorKind.UNAVAILABLE, "The shared provider cache is unavailable; skipped."
        )
    return await fetch()


async def _store_quietly(prepared: Prepared, response: httpx.Response) -> bool:
    settings = get_settings()
    if not 200 <= response.status_code < 300:
        return False
    if len(response.content) > settings.provider_cache_max_bytes:
        logger.info("Not caching an oversized %s response", prepared.source)
        return False
    try:
        await store.save(prepared.key, prepared.source, response, prepared.ttl)
    except Exception:
        logger.warning("Could not store a %s response in the cache", prepared.source)
        return False
    cache_stats.record(prepared.name, "stored")
    return True


async def _release_quietly(prepared: Prepared, owner: uuid.UUID) -> None:
    try:
        await store.release(prepared.key, owner)
    except Exception:
        logger.warning("Could not release a provider cache lease (%s)", prepared.source)


async def _load(
    prepared: Prepared, fetch: Callable[[], Awaitable[httpx.Response]]
) -> httpx.Response:
    """Level 2 lookup and lease-guarded fetch (runs once per key per process)."""
    if not persists(prepared.name, prepared.policy):
        cache_stats.record(prepared.name, "miss")
        return await fetch()
    settings = get_settings()
    stale = settings.provider_cache_stale_seconds
    try:
        row = await store.load(prepared.key, stale)
        if row and row.fresh and row.usable:
            cache_stats.record(prepared.name, "db_hit")
            return _response(prepared, row)
        owner = uuid.uuid4()
        claimed = await store.claim(
            prepared.key, prepared.source, owner, settings.provider_cache_lease_seconds
        )
        if not claimed:
            cache_stats.record(prepared.name, "lease_wait")
            deadline = time.monotonic() + settings.provider_cache_wait_seconds
            while not claimed and time.monotonic() < deadline:
                await asyncio.sleep(POLL_SECONDS)
                row = await store.load(prepared.key, stale)
                if row and row.fresh and row.usable:
                    cache_stats.record(prepared.name, "db_hit")
                    return _response(prepared, row)
                if row is None or not row.leased:  # the owner gave up or died
                    claimed = await store.claim(
                        prepared.key,
                        prepared.source,
                        owner,
                        settings.provider_cache_lease_seconds,
                    )
            if not claimed:
                cache_stats.record(prepared.name, "lease_timeout")
    except Exception:
        return await _db_failed(prepared, fetch)

    cache_stats.record(prepared.name, "miss")
    try:
        response = await fetch()
    except BaseException:
        if claimed:
            await asyncio.shield(_release_quietly(prepared, owner))
        raise
    stored = await _store_quietly(prepared, response)
    if claimed and not stored:
        await _release_quietly(prepared, owner)
    return response


async def get_or_fetch(
    prepared: Prepared, fetch: Callable[[], Awaitable[httpx.Response]]
) -> httpx.Response:
    from app.sources.base import request_cache

    return await request_cache.get_or_fetch(
        f"sha256:{prepared.key}",
        lambda: _load(prepared, fetch),
        ttl=prepared.ttl,
        label=prepared.name,
    )


async def stale_response(prepared: Prepared) -> httpx.Response | None:
    """An expired-but-recent stored response (used while a provider cools
    down), or None. Only providers that may be persisted have one."""
    if not persists(prepared.name, prepared.policy):
        return None
    try:
        row = await store.load(prepared.key, get_settings().provider_cache_stale_seconds)
    except Exception:
        return None
    if row and row.usable and row.stale_ok:
        cache_stats.record(prepared.name, "stale_served")
        return _response(prepared, row)
    return None
